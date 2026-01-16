import os
from datetime import datetime, timedelta, timezone
import requests
import pdfplumber
import fitz  # PyMuPDF
from playwright.sync_api import sync_playwright
from gtts import gTTS

# ================= CONFIG =================
CASE_IDS = ["288/06/IP"]   # <<< ONLY CHANGE THIS
SITE_BASE = "https://www.colchc.gov.lk/daily-court-lists"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_IDS_RAW = os.environ.get("CHAT_IDS", "")
CHAT_IDS = [int(x) for x in CHAT_IDS_RAW.split(",") if x.strip()]

if not BOT_TOKEN or not CHAT_IDS:
    print("❌ BOT_TOKEN or CHAT_IDS not set. Exiting.")
    exit(1)

DOWNLOAD_DIR = "/tmp/court"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
# ==========================================

SL_TZ = timezone(timedelta(hours=5, minutes=30))

# Current date in Sri Lanka
today = datetime.now(tz=SL_TZ).date()
#today = today - timedelta(days=1)
day = str(today.day)
month = str(today.month)
year = str(today.year)
MONTH_NAME = today.strftime("%B").lower()
SITE_URL = f"{SITE_BASE}/{year}/{MONTH_NAME}"

selector = (
    f'td.cal-date-picker'
    f'[data-date="{day}"]'
    f'[data-month="{month}"]'
    f'[data-year="{year}"]'
)

pdf_path = f"{DOWNLOAD_DIR}/cause_{year}_{month}_{day}.pdf"
marked_pdf = f"{DOWNLOAD_DIR}/cause_MARKED_{year}_{month}_{day}.pdf"
voice_path = f"{DOWNLOAD_DIR}/alert.mp3"

# ============ DOWNLOAD PDF ============
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    page.goto(SITE_URL, timeout=90000)
    page.wait_for_selector(selector, timeout=90000)

    # Use expect_download context manager for CI-friendly downloads
download = None

try:
    with page.expect_download(timeout=15000):
        page.click(selector)
    download = page.wait_for_event("download", timeout=15000)
except:
    print("ℹ️ No PDF available for today. Exiting safely.")

if not download:
    browser.close()
    exit(0)

download.save_as(pdf_path)


# ============ READ PDF ============
text = ""
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text += page.extract_text() or ""

found = [c for c in CASE_IDS if c.lower() in text.lower()]

if not found:
    print("No case found today.")
    exit(0)

# ============ MARK PDF ============
doc = fitz.open(pdf_path)
for page in doc:
    for case in found:
        for rect in page.search_for(case):
            annot = page.add_rect_annot(rect)
            annot.set_colors(stroke=(1, 0, 0))
            annot.set_border(width=2)
            annot.update()
doc.save(marked_pdf)
doc.close()

# ============ VOICE ============
voice_text = (
    f"Alert. Your court case {', '.join(found)} "
    f"is listed today, {today.strftime('%d %B %Y')}."
)
gTTS(text=voice_text, lang="en").save(voice_path)

# ============ TELEGRAM ============
message = (
    "⚖️ *Court Case Listed*\n\n"
    f"📅 Date: {today.strftime('%d-%m-%Y')}\n"
    f"📌 Case: {', '.join(found)}"
)

for chat_id in CHAT_IDS:
    # Send message
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    )

    # Send voice alert
    with open(voice_path, "rb") as v:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendVoice",
            data={"chat_id": chat_id},
            files={"voice": v}
        )

    # Send marked PDF
    with open(marked_pdf, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
            data={"chat_id": chat_id},
            files={"document": f}
        )

print("✅ Telegram alert sent")
