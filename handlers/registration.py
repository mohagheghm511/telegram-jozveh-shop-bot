import re
import aiosqlite
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
from telegram import KeyboardButton as KBtn, ReplyKeyboardMarkup as RKb
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.db import DB_PATH, get_text, get_setting
from config.config import *

# ─── لیست استان‌ها و شهرها ───────────────────────────────────────────────────
PROVINCES = {
    "تهران":           ["تهران","کرج","اسلامشهر","شهریار","قدس","ملارد","ورامین","پاکدشت","رباط‌کریم","پردیس"],
    "اصفهان":          ["اصفهان","کاشان","نجف‌آباد","خمینی‌شهر","شاهین‌شهر","فلاورجان","مبارکه","زرین‌شهر","شهرضا","گلپایگان"],
    "البرز":           ["کرج","فردیس","نظرآباد","ساوجبلاغ","هشتگرد","محمدشهر","مشکین‌دشت","ماهدشت","چهارباغ","طالقان"],
    "گیلان":           ["رشت","بندرانزلی","لاهیجان","لنگرود","رودسر","آستارا","تالش","صومعه‌سرا","فومن","ماسال"],
    "مازندران":        ["ساری","بابل","آمل","قائم‌شهر","نوشهر","چالوس","تنکابن","محمودآباد","بهشهر","رامسر"],
    "آذربایجان غربی": ["ارومیه","خوی","میاندوآب","بوکان","مهاباد","سلماس","پیرانشهر","سردشت","ماکو","نقده"],
    "آذربایجان شرقی": ["تبریز","مراغه","مرند","میانه","اهر","بناب","شبستر","آذرشهر","هشترود","سراب"],
    "خوزستان":         ["اهواز","آبادان","خرمشهر","دزفول","اندیمشک","ماهشهر","شوش","شوشتر","مسجدسلیمان","بهبهان"],
    "خراسان رضوی":    ["مشهد","نیشابور","سبزوار","تربت حیدریه","قوچان","کاشمر","تربت جام","چناران","سرخس","تایباد"],
    "فارس":            ["شیراز","مرودشت","کازرون","جهرم","فسا","لار","داراب","نی‌ریز","فیروزآباد","آباده"],
}


def validate_national_id(nid: str) -> bool:
    nid = nid.strip()
    if not re.match(r'^\d{10}$', nid):
        return False
    if len(set(nid)) == 1:
        return False
    return True


def validate_phone(phone: str) -> bool:
    phone = phone.strip().replace(" ", "").replace("-", "")
    return bool(re.match(r'^09[0-9]{9}$', phone))


async def check_join(context, user_id: int) -> tuple[bool, list]:
    active = await get_setting("join_channels_active", "1")
    if active != "1":
        return True, []
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id, channel_name FROM join_channels WHERE is_active=1"
        ) as c:
            channels = await c.fetchall()
    if not channels:
        return True, []
    not_joined = []
    for row in channels:
        ch_id, ch_name = row[0], row[1]
        try:
            ch_id_clean = ch_id.strip()
            chat_id = int(ch_id_clean) if ch_id_clean.lstrip('-').isdigit() else ch_id_clean
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status in ("left", "kicked", "banned"):
                not_joined.append((ch_id, ch_name))
        except:
            not_joined.append((ch_id, ch_name))
    return len(not_joined) == 0, not_joined


async def send_join_required(update_or_msg, context, not_joined: list):
    text = await get_text("join_required")
    if not text:
        text = "برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید 👇"
    rows = []
    for item in not_joined:
        ch_id   = item[0].strip()
        ch_name = item[1]
        if ch_id.startswith("@"):
            url = f"https://t.me/{ch_id.lstrip('@')}"
        elif ch_id.lstrip('-').isdigit():
            numeric = ch_id.replace("-100", "")
            url = f"https://t.me/c/{numeric}/1"
        else:
            url = f"https://t.me/{ch_id}"
        rows.append([Btn(f"📢 {ch_name}", url=url)])

    btn_text = await get_text("join_check_btn")
    if not btn_text:
        btn_text = "✅ عضو شدم، بررسی کن"
    rows.append([Btn(btn_text, callback_data="check_join")])

    if hasattr(update_or_msg, 'message') and update_or_msg.message:
        await update_or_msg.message.reply_text(text, reply_markup=Kb(rows))
    elif hasattr(update_or_msg, 'reply_text'):
        await update_or_msg.reply_text(text, reply_markup=Kb(rows))


async def is_profile_done(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT profile_done FROM users WHERE tg_id=?", (user_id,)) as c:
            row = await c.fetchone()
    return bool(row and row[0])


# ─── CHECK JOIN ───────────────────────────────────────────────────────────────
async def handle_check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = update.effective_user.id
    ok, not_joined = await check_join(context, uid)
    if not ok:
        await q.answer(await get_text("join_not_done") or "❌ هنوز عضو نشده‌اید!", show_alert=True)
        return
    await q.answer()
    if not await is_profile_done(uid):
        await start_registration(q.message, context, uid)
    else:
        from handlers.user import send_main_menu
        await send_main_menu(update, context)


# ─── REGISTRATION ─────────────────────────────────────────────────────────────
async def start_registration(msg, context, uid: int):
    context.user_data["reg_step"] = "full_name"
    welcome = await get_text("register_welcome") or "👋 خوش آمدید!"
    ask = await get_text("ask_full_name") or "📝 نام و نام خانوادگی:"
    await msg.reply_text(f"{welcome}\n\n{ask}")


async def _show_provinces(msg_or_query, context, edit=False):
    """نمایش لیست استان‌ها"""
    rows = []
    provinces = list(PROVINCES.keys())
    for i in range(0, len(provinces), 2):
        row = [Btn(provinces[i], callback_data=f"province_{provinces[i]}")]
        if i+1 < len(provinces):
            row.append(Btn(provinces[i+1], callback_data=f"province_{provinces[i+1]}"))
        rows.append(row)

    ask = await get_text("ask_city") or "🏙️ استان خود را انتخاب کنید:"
    if edit:
        await msg_or_query.edit_message_text(ask, reply_markup=Kb(rows))
    else:
        await msg_or_query.reply_text(ask, reply_markup=Kb(rows))


async def _show_cities(query, province: str):
    """نمایش شهرهای یک استان"""
    cities = PROVINCES.get(province, [])
    rows = []
    for i in range(0, len(cities), 2):
        row = [Btn(cities[i], callback_data=f"city_{cities[i]}")]
        if i+1 < len(cities):
            row.append(Btn(cities[i+1], callback_data=f"city_{cities[i+1]}"))
        rows.append(row)
    rows.append([Btn("🔙 بازگشت به استان‌ها", callback_data="back_provinces")])
    await query.edit_message_text(f"🏙️ استان {province}\nشهر خود را انتخاب کنید:", reply_markup=Kb(rows))


async def handle_province_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب استان"""
    q = update.callback_query
    await q.answer()
    province = q.data.replace("province_", "")
    context.user_data["reg_province"] = province
    await _show_cities(q, province)


async def handle_city_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب شهر"""
    q = update.callback_query
    await q.answer()
    city = q.data.replace("city_", "")
    uid  = update.effective_user.id

    step = context.user_data.get("reg_step")

    if step == "city":
        context.user_data["reg_city"] = city
        context.user_data["reg_step"] = "grade"
        await q.edit_message_text(f"✅ شهر {city} انتخاب شد.")
        await context.bot.send_message(uid, await get_text("ask_grade") or "🎓 پایه تحصیلی:")

    elif step == "edit_city":
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET city=? WHERE tg_id=?", (city, uid))
            await db.commit()
        context.user_data["reg_step"] = None
        from handlers.user import get_reply_keyboard
        rk = await get_reply_keyboard(uid)
        await q.edit_message_text(f"✅ شهر به {city} تغییر کرد.")
        await context.bot.send_message(uid, await get_text("profile_edit_done") or "✅ ویرایش شد.", reply_markup=rk)


async def handle_back_provinces(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await _show_provinces(q, context, edit=True)


async def handle_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("reg_step")
    if not step:
        return False

    uid  = update.effective_user.id
    text = ""
    if update.message.text:
        text = update.message.text.strip()
    elif update.message.contact:
        text = update.message.contact.phone_number or ""

    if step == "full_name":
        if len(text) < 3:
            await update.message.reply_text("❌ نام و نام خانوادگی خیلی کوتاه است.")
            return True
        context.user_data["reg_full_name"] = text
        context.user_data["reg_step"] = "national_id"
        await update.message.reply_text(await get_text("ask_national_id") or "🪪 کد ملی:")

    elif step == "national_id":
        nid = text.replace("-","").replace(" ","")
        nid = nid.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹","0123456789"))
        if not validate_national_id(nid):
            await update.message.reply_text(await get_text("national_id_invalid") or "❌ کد ملی نامعتبر.")
            return True
        context.user_data["reg_national_id"] = nid
        context.user_data["reg_step"] = "phone"
        kb = RKb([[KBtn(await get_text("share_phone_btn") or "📱 اشتراک‌گذاری شماره", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(await get_text("ask_phone") or "📱 شماره موبایل:", reply_markup=kb)

    elif step == "phone":
        phone = text
        if update.message.contact:
            phone = update.message.contact.phone_number or text
        phone = str(phone).strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹","0123456789"))
        phone = phone.replace(" ","").replace("-","")
        if phone.startswith("+98"):   phone = "0" + phone[3:]
        elif phone.startswith("98") and len(phone)==12: phone = "0" + phone[2:]
        elif phone.startswith("9") and len(phone)==10:  phone = "0" + phone
        if not validate_phone(phone):
            await update.message.reply_text(await get_text("phone_invalid") or "❌ شماره نامعتبر.")
            return True
        context.user_data["reg_phone"] = phone
        context.user_data["reg_step"]  = "city"
        # حذف دکمه اشتراک‌گذاری شماره با ReplyKeyboardRemove
        from telegram import ReplyKeyboardRemove
        await update.message.reply_text("✅ شماره دریافت شد.", reply_markup=ReplyKeyboardRemove())
        await _show_provinces(update.message, context)

    elif step == "grade":
        if len(text) < 1:
            await update.message.reply_text("❌ پایه تحصیلی معتبر نیست.")
            return True
        context.user_data["reg_grade"] = text
        context.user_data["reg_step"]  = None
        await _save_profile(uid, context)
        await update.message.reply_text(await get_text("register_done") or "✅ ثبت‌نام کامل شد!")
        from handlers.user import send_main_menu
        await send_main_menu(update, context)

    return True


async def _save_profile(uid: int, context):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET first_last_name=?, national_id=?, phone=?, city=?, grade=?, profile_done=1
            WHERE tg_id=?
        """, (
            context.user_data.get("reg_full_name",""),
            context.user_data.get("reg_national_id",""),
            context.user_data.get("reg_phone",""),
            context.user_data.get("reg_city",""),
            context.user_data.get("reg_grade",""),
            uid
        ))
        await db.commit()
    for k in ["reg_full_name","reg_national_id","reg_phone","reg_city","reg_grade","reg_step","reg_province"]:
        context.user_data.pop(k, None)


# ─── PROFILE EDIT ─────────────────────────────────────────────────────────────
async def show_profile_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT first_last_name,national_id,phone,city,grade FROM users WHERE tg_id=?", (uid,)
        ) as c:
            u = await c.fetchone()
    text = (f"👤 <b>اطلاعات پروفایل</b>\n────────────────\n"
            f"📝 نام: {u[0] or '—'}\n🪪 کد ملی: {u[1] or '—'}\n"
            f"📱 موبایل: {u[2] or '—'}\n🏙️ شهر: {u[3] or '—'}\n🎓 پایه: {u[4] or '—'}")
    kb = [
        [Btn("✏️ ویرایش نام",  callback_data="edit_prof_full_name"),
         Btn("✏️ کد ملی",      callback_data="edit_prof_national_id")],
        [Btn("✏️ موبایل",      callback_data="edit_prof_phone"),
         Btn("✏️ شهر",         callback_data="edit_prof_city")],
        [Btn("✏️ پایه",        callback_data="edit_prof_grade")],
        [Btn("🔙 بازگشت",      callback_data="profile")],
    ]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def handle_edit_profile_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    field = q.data.replace("edit_prof_", "")
    context.user_data["reg_step"] = f"edit_{field}"

    if field == "city":
        await _show_provinces(q, context, edit=True)
        return

    prompts = {
        "full_name":   "ask_full_name",
        "national_id": "ask_national_id",
        "phone":       "ask_phone",
        "grade":       "ask_grade",
    }
    prompt_key = prompts.get(field, "ask_full_name")
    uid = update.effective_user.id

    if field == "phone":
        kb = RKb([[KBtn(await get_text("share_phone_btn") or "📱 اشتراک‌گذاری", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
        await context.bot.send_message(uid, await get_text(prompt_key) or "📱 شماره:", reply_markup=kb)
    else:
        await context.bot.send_message(uid, await get_text(prompt_key) or "مقدار جدید:")


async def handle_edit_profile_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    step = context.user_data.get("reg_step", "")
    if not step.startswith("edit_"):
        return False

    field = step.replace("edit_", "")
    if field == "city":
        return False  # city با callback هندل میشه

    uid = update.effective_user.id
    val = update.message.text.strip() if update.message.text else ""
    if update.message.contact:
        val = update.message.contact.phone_number or ""

    if field == "national_id":
        val = val.replace("-","").replace(" ","").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹","0123456789"))
        if not validate_national_id(val):
            await update.message.reply_text(await get_text("national_id_invalid") or "❌ کد ملی نامعتبر.")
            return True
    elif field == "phone":
        val = str(val).translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹","0123456789")).replace(" ","").replace("-","")
        if val.startswith("+98"):   val = "0" + val[3:]
        elif val.startswith("98") and len(val)==12: val = "0" + val[2:]
        elif val.startswith("9") and len(val)==10:  val = "0" + val
        if not validate_phone(val):
            await update.message.reply_text(await get_text("phone_invalid") or "❌ شماره نامعتبر.")
            return True

    col_map = {"full_name":"first_last_name","national_id":"national_id","phone":"phone","grade":"grade"}
    col = col_map.get(field)
    if col:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(f"UPDATE users SET {col}=? WHERE tg_id=?", (val, uid))
            await db.commit()

    context.user_data["reg_step"] = None
    from handlers.user import get_reply_keyboard
    from telegram import ReplyKeyboardRemove
    rk = await get_reply_keyboard(uid)
    # اگه فیلد phone بود، ابتدا keyboard رو حذف کن بعد منوی اصلی رو نشون بده
    if field == "phone":
        await update.message.reply_text("✅ شماره ذخیره شد.", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text(await get_text("profile_edit_done") or "✅ ویرایش شد.", reply_markup=rk)
    return True