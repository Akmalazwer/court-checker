import os
import datetime
import requests
import pdfplumber
import fitz  # PyMuPDF
from playwright.sync_api import sync_playwright
from gtts import gTTS
from datetime import timezone, timedelta

# ================= CONFIG =================
CASE_IDS = ["141/24/MR"]

SITE_BASE = "https://www.colchc.gov.lk/daily-court-lists"

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_IDS_RAW = os.environ.get("CHAT_IDS", "")
CHAT_IDS = [int(x) for x in CHAT_IDS_RAW.split(",") if x.strip()]

if not BOT_TOKEN or not CHAT_IDS:
    print("❌ BOT_TOKEN or CHAT_IDS not set. Exiting.")
    exit(1)

# -------- Sri Lanka Timezone --------
SL_TZ = timezone(timedelta(hours=5, minutes=30))

# -------- TEST DATE (13 January) ----
TEST_DATE = datetime.date(2025, 1, 13)

today_sl = datetime.datetime.now(SL_TZ)
print("🕒 Workflow Time (UTC):", datetime.datetime.now(timezone.utc))
print("🕒 Workflow Time (SL): ", today_sl)
print("📅 Checking court list for:", TEST_DATE)

day = str(TEST_DATE.day)
month = str(TEST_DATE.month)
year = str(TEST_DATE.year)

MONTH_NAME = TEST_DATE.strftime("%B").lower()
SITE_URL = f"{SITE_BASE}/{year}/{MONTH_NAME}"

DOWNLOAD_DIR = "/tmp/court"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

pdf_path = f"{DOWNLOAD_DIR}/cause_{year}_{month}_{day}.pdf"
marked_pdf = f"{DOWNLOAD_DIR}/cause_MARKED_{year}_{month}_{day}.pdf"
voice_path = f"{DOWNLOAD_DIR}/alert.mp3"

selector = (
    f'td.cal-date-picker'
    f'[data-date="{day}"]'
    f'[data-month="{month}"]'
    f'[data-year="{year}"]'
)

# ================= DOWNLOAD PDF =================
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()

    page.goto(SITE_URL, timeout=60000)
    page.wait_for_selector(selector, timeout=60000)

download = None

try:
    with page.expect_download(timeout=15000) as d:
        page.click(selector)
    download = d.value
except Exception:
    print("⚠️ No PDF download available for this date.")
    browser.close()
    exit(0)

download.save_as(pdf_path)
browser.close()


print("✅ PDF downloaded")

# ================= READ PDF =================
text = ""
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text += page.extract_text() or ""

found = [c for c in CASE_IDS if c.lower() in text.lower()]

if not found:
    print("ℹ️ No case found for this date.")
    exit(0)

print("⚖️ Case found:", found)

# ================= MARK PDF =================
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

print("✅ PDF marked")

# ================= VOICE =================
voice_text = (
    f"Alert. Your court case {', '.join(found)} "
    f"is listed on {TEST_DATE.strftime('%d %B %Y')}."
)
gTTS(text=voice_text, lang="en").save(voice_path)

# ================= TELEGRAM =================
message = (
    "⚖️ *Court Case Listed*\n\n"
    f"📅 Date: {TEST_DATE.strftime('%d-%m-%Y')}\n"
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

print("✅ Telegram alert sent successfully")
