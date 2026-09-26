import os
from pathlib import Path

# لود کردن فایل .env بدون نیاز به python-dotenv
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# ─── تنها دو چیز از محیط خوانده می‌شود ─────────────────────────────────────
# ۱. توکن ربات (از @BotFather)
# ۲. آیدی ادمین‌ها
# همه چیز دیگر از پنل ادمین داخل ربات تنظیم می‌شود.

BOT_TOKEN  = os.getenv("BOT_TOKEN", "")
ADMIN_IDS  = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip().isdigit()]

FILES_DIR = "files"
TEMP_DIR  = "temp"
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(TEMP_DIR,  exist_ok=True)

# ─── حالت‌های مکالمه ─────────────────────────────────────────────────────────
(
    ST_IDLE,
    ST_AWAIT_RECEIPT,
    ST_AWAIT_REJECT_REASON,
    ST_AWAIT_COUPON,
    ST_AWAIT_BROADCAST,
    ST_AWAIT_PROD_FILE,
    ST_AWAIT_PROD_TITLE,
    ST_AWAIT_PROD_DESC,
    ST_AWAIT_PROD_PRICE,
    ST_AWAIT_PROD_CAT,
    ST_AWAIT_CAT_NAME,
    ST_AWAIT_COUP_CODE,
    ST_AWAIT_COUP_VALUE,
    ST_AWAIT_COUP_TYPE,
    ST_AWAIT_COUP_MAX,
    ST_AWAIT_EDIT_TEXT,
    ST_AWAIT_EDIT_SETTING,
    ST_AWAIT_WALLET_AMT,
    ST_AWAIT_EDIT_PROD_VAL,
    ST_AWAIT_GRADE_NAME,
    ST_AWAIT_COUP_PER_USER,
    ST_AWAIT_CHANNEL_INFO,
) = range(22)


def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS
