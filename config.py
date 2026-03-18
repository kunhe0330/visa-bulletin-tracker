import os
from datetime import datetime

# Telegram
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# User settings
PRIORITY_DATE = datetime.strptime(
    os.environ.get("PRIORITY_DATE", "2025-10-31"), "%Y-%m-%d"
).date()
CHARGEABILITY = os.environ.get("CHARGEABILITY", "ALL_OTHER")

# Schedule
CHECK_HOUR_KST = int(os.environ.get("CHECK_HOUR_KST", "9"))
TIMEZONE = os.environ.get("TIMEZONE", "Asia/Seoul")

# Flask
PORT = int(os.environ.get("PORT", "8080"))

# Paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
STATE_FILE = os.path.join(DATA_DIR, "bulletin_state.json")

# Scraping
BASE_URL = "https://travel.state.gov"
BULLETIN_INDEX_URL = f"{BASE_URL}/content/travel/en/legal/visa-law0/visa-bulletin.html"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
MAX_RETRIES = 3
RETRY_DELAY = 3  # seconds
