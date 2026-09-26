"""
واترمارک اختصاصی فایل‌ها برای هر خریدار

هر فایلی که به خریدار ارسال می‌شود، نام، شماره موبایل و کد ملی خود او را روی
صفحه‌ها دارد. اگر فایل پخش شود، معلوم است از حساب چه کسی بیرون رفته.

- PDF: متن مورب کم‌رنگ وسط هر صفحه + یک سطر اطلاعات در پایین صفحه
- تصویر (jpg / png / webp): متن مورب تکرارشونده روی کل تصویر
- سایر فرمت‌ها (Word، PowerPoint، Excel، zip...): بدون تغییر کپی می‌شوند و
  فقط با protect_content ارسال می‌شوند (جلوی فوروارد و ذخیره را می‌گیرد).

متن فارسی با فونت وزیرمتن (assets/fonts) و کتابخانه‌های arabic-reshaper و
python-bidi درست چیده می‌شود. اگر این کتابخانه‌ها نصب نباشند، فقط بخش‌های
لاتین/عددی (موبایل و کد ملی) چاپ می‌شود تا واترمارک هرگز خراب نشود.
"""
import asyncio
import io
import logging
import os
import shutil

log = logging.getLogger(__name__)

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "assets", "fonts", "Vazirmatn-Regular.ttf")
FONT_NAME = "Vazirmatn"

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _RTL_OK = True
except ImportError:
    _RTL_OK = False


def _has_persian(text: str) -> bool:
    return any("؀" <= ch <= "ۿ" for ch in text)


def _shape(text: str) -> str:
    """آماده‌سازی متن فارسی برای رسم (اتصال حروف + راست‌به‌چپ)"""
    if not text:
        return ""
    if _has_persian(text):
        if not _RTL_OK or not os.path.exists(FONT_PATH):
            # بدون ابزار شکل‌دهی، فارسی را حذف می‌کنیم تا حروف جدا و به‌هم‌ریخته چاپ نشود
            return "".join(ch for ch in text if ord(ch) < 128).strip()
        return get_display(arabic_reshaper.reshape(text))
    return text


def _to_latin_digits(text: str) -> str:
    return str(text or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


def _build_lines(user_name, phone, school, national_id):
    phone       = _to_latin_digits(phone if phone and phone != "—" else "")
    national_id = _to_latin_digits(national_id)
    main = " | ".join(x for x in [user_name, phone] if x)
    ids  = f"ID: {national_id}" if national_id else ""
    foot = " | ".join(x for x in [school, user_name, phone, national_id] if x)
    return _shape(main), ids, _shape(foot)


# ─── PDF ─────────────────────────────────────────────────────────────────────
def _watermark_pdf(src, dst, user_name, phone, school, national_id):
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font = "Helvetica"
    if os.path.exists(FONT_PATH):
        if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
        font = FONT_NAME

    main, ids, foot = _build_lines(user_name, phone, school, national_id)

    reader = PdfReader(src)
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            shutil.copyfile(src, dst)  # PDF قفل‌دار — بدون تغییر
            return

    overlays = {}  # یک لایه برای هر اندازه صفحه
    writer = PdfWriter()
    for page in reader.pages:
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        key = (round(w), round(h))
        if key not in overlays:
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(w, h))
            size = max(14, min(w, h) / 18)
            # متن مورب وسط صفحه
            c.saveState()
            c.setFillColorRGB(0.5, 0.5, 0.5, alpha=0.18)
            c.translate(w / 2, h / 2)
            c.rotate(35)
            c.setFont(font, size)
            if main:
                c.drawCentredString(0, size * 0.6, main)
            if ids:
                c.setFont(font, size * 0.8)
                c.drawCentredString(0, -size * 0.8, ids)
            c.restoreState()
            # سطر اطلاعات پایین صفحه
            if foot:
                c.setFillColorRGB(0.35, 0.35, 0.35, alpha=0.6)
                c.setFont(font, 8)
                c.drawCentredString(w / 2, 12, foot)
            c.save()
            buf.seek(0)
            overlays[key] = PdfReader(buf).pages[0]
        page.merge_page(overlays[key])
        writer.add_page(page)

    with open(dst, "wb") as f:
        writer.write(f)


# ─── IMAGE ───────────────────────────────────────────────────────────────────
def _watermark_image(src, dst, ext, user_name, phone, school, national_id):
    from PIL import Image, ImageDraw, ImageFont

    from PIL import features
    if features.check("raqm"):
        # Pillow با libraqm خودش حروف فارسی را می‌چسباند و راست‌به‌چپ می‌کند؛
        # متن خام می‌دهیم تا دو بار برعکس نشود.
        phone_l = _to_latin_digits(phone if phone and phone != "—" else "")
        main = " | ".join(x for x in [user_name, phone_l] if x)
        nid  = _to_latin_digits(national_id)
        ids  = f"ID: {nid}" if nid else ""
    else:
        main, ids, _ = _build_lines(user_name, phone, school, national_id)
    text = "   ".join(x for x in [main, ids] if x) or "protected"

    base = Image.open(src).convert("RGBA")
    W, H = base.size
    size = max(16, min(W, H) // 22)
    try:
        font = ImageFont.truetype(FONT_PATH, size)
    except Exception:
        font = ImageFont.load_default()

    # یک کاشی متن مورب می‌سازیم و روی کل تصویر تکرار می‌کنیم
    tw = int(ImageDraw.Draw(base).textlength(text, font=font)) + size * 2
    tile = Image.new("RGBA", (tw, size * 3), (0, 0, 0, 0))
    ImageDraw.Draw(tile).text((size, size), text, font=font, fill=(80, 80, 80, 85))
    tile = tile.rotate(30, expand=True)

    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    step_x, step_y = tile.width, int(tile.height * 1.1)
    for y in range(-tile.height, H + tile.height, max(step_y, 1)):
        for x in range(-tile.width, W + tile.width, max(step_x, 1)):
            layer.paste(tile, (x, y), tile)

    out = Image.alpha_composite(base, layer)
    if ext in ("jpg", "jpeg"):
        out.convert("RGB").save(dst, "JPEG", quality=92)
    elif ext == "webp":
        out.save(dst, "WEBP", quality=92)
    else:
        out.save(dst, "PNG")


# ─── PUBLIC API ──────────────────────────────────────────────────────────────
def _apply(src, ext, user_name, phone, school, dst, national_id):
    ext = (ext or "").lower()
    try:
        if ext == "pdf":
            _watermark_pdf(src, dst, user_name, phone, school, national_id)
        elif ext in IMAGE_EXTS:
            _watermark_image(src, dst, ext, user_name, phone, school, national_id)
        else:
            shutil.copyfile(src, dst)
    except Exception as e:  # هر خطایی → فایل اصلی ارسال شود، خرید نباید گیر کند
        log.warning("watermark failed for %s: %s — sending original", src, e)
        shutil.copyfile(src, dst)


async def apply_watermark(src, ext, user_name, phone, school, dst, national_id=""):
    """واترمارک در یک thread جدا اجرا می‌شود تا ربات در این مدت قفل نشود."""
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    await asyncio.to_thread(_apply, src, ext, user_name, phone, school, dst, national_id)
