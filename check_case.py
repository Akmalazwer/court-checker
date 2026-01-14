import os
import datetime
import requests
import pdfplumber
import fitz  # PyMuPDF
from playwright.sync_api import sync_playwright
from gtts import gTTS

# ================= CONFIG =================
CASE_IDS = ["141/24/MR"]   # <<< ONLY CHANGE THIS
SITE_BASE = "https://www.colchc.gov.lk/daily-court-lists"


CHAT_IDS_RAW = os.environ.get("CHAT_IDS", "")
CHAT_IDS = [int(x) for x in CHAT_IDS_RAW.split(",") if x.strip()]

DOWNLOAD_DIR = "/tmp/court"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
# ==========================================

today = datetime.date.today()
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

    page.goto(SITE_URL, timeout=60000)
    page.wait_for_selector(selector, timeout=60000)

    with page.expect_download():
        page.click(selector)

    download = page.wait_for_event("download")
    download.save_as(pdf_path)
    browser.close()

# ============ READ PDF ============
text = ""
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text += page.extract_text() or ""

found = [c for c in CASE_IDS if c.lower() in text.lower()]

if not found:
    print("No case found today.")
    exit()

# ============ MARK PDF ============
doc = fitz.open(pdf_path)
for page in doc:
    for case in found:
        for rect in page.search_for(case):
            box = page.add_rect_annot(rect)
            box.set_colors(stroke=(1, 0, 0))
            box.set_border(width=2)
            box.update()
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
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    )

    with open(voice_path, "rb") as v:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendVoice",
            data={"chat_id": chat_id},
            files={"voice": v}
        )

    with open(marked_pdf, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
            data={"chat_id": chat_id},
            files={"document": f}
        )

print("✅ Telegram alert sent")
