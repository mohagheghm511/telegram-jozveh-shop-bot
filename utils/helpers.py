"""توابع کمکی عمومی ربات"""
import os
import secrets
import string
from datetime import datetime

try:
    import jdatetime
except ImportError:  # jdatetime اختیاری است
    jdatetime = None


def fmt(value) -> str:
    """نمایش عدد با جداکننده هزارگان: 125000 → 125,000"""
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return str(value)


def gen_ref_code(length: int = 8) -> str:
    """کد معرف تصادفی و یکتا (حروف بزرگ + عدد)"""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def now_str() -> str:
    """تاریخ و ساعت فعلی — شمسی اگر jdatetime نصب باشد"""
    if jdatetime:
        return jdatetime.datetime.now().strftime("%Y/%m/%d %H:%M")
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def chunks(items, size: int):
    """تقسیم لیست به تکه‌های چندتایی (برای چیدن دکمه‌ها در ردیف)"""
    items = list(items)
    return [items[i:i + size] for i in range(0, len(items), size)]


def file_ext(filename: str) -> str:
    """پسوند فایل بدون نقطه و با حروف کوچک: 'Book.PDF' → 'pdf'"""
    if not filename:
        return "bin"
    ext = os.path.splitext(filename)[1].lstrip(".").lower()
    return ext or "bin"
