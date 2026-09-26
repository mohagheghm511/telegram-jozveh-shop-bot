import os
import aiosqlite
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.db import DB_PATH, get_text, get_all_texts, set_text, get_setting, set_setting, get_all_settings
from config.config import *
from utils.helpers import fmt, now_str, chunks, file_ext


def _is_emoji(char: str) -> bool:
    """تشخیص اینکه کاراکتر اول emoji هست یا نه (نه حرف فارسی/عربی)"""
    cp = ord(char)
    return (
        0x1F300 <= cp <= 0x1FAFF or  # Emoji اصلی
        0x2600  <= cp <= 0x27BF  or  # Symbols
        0x1F000 <= cp <= 0x1F02F or  # Mahjong
        cp in (0x200D, 0xFE0F)       # ZWJ و variation selector
    )


# ─── ADMIN PANEL ─────────────────────────────────────────────────────────────
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    q = update.callback_query

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            users = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*),SUM(total_amount) FROM orders WHERE status='approved'") as c:
            all_o = await c.fetchone()
        async with db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'") as c:
            pend  = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM products WHERE is_active=1") as c:
            prods = (await c.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*),SUM(total_amount) FROM orders WHERE status='approved' AND date(created_at)=date('now')"
        ) as c:
            today = await c.fetchone()

    text = (
        f"⚙️ <b>پنل مدیریت</b>\n────────────────\n"
        f"👥 کاربران: {users}\n"
        f"📚 جزوات فعال: {prods}\n"
        f"⏳ در انتظار تأیید: {pend}\n"
        f"📅 فروش امروز: {today[0]} | {fmt(today[1] or 0)} ت\n"
        f"📈 کل فروش: {all_o[0]} | {fmt(all_o[1] or 0)} ت\n"
        f"────────────────\n🕐 {now_str()}"
    )
    kb = [
        [Btn("📚 جزوات",          callback_data="adm_prods"),
         Btn("🎓 پایه‌ها",         callback_data="adm_grades")],
        [Btn("📂 دسته‌بندی‌ها",   callback_data="adm_cats"),
         Btn("👥 کاربران",         callback_data="adm_users")],
        [Btn("📦 سفارشات",         callback_data="adm_orders"),
         Btn("🎟️ کدهای تخفیف",    callback_data="adm_coupons")],
        [Btn("📊 آمار فروش",       callback_data="adm_stats"),
         Btn("📢 پیام انبوه",      callback_data="adm_broadcast")],
        [Btn("👛 کیف‌پول‌ها",     callback_data="adm_wallets"),
         Btn("✏️ متون ربات",       callback_data="adm_texts")],
        [Btn("⚙️ تنظیمات ربات",   callback_data="adm_settings")],
        [Btn("📢 کانال‌های عضویت",  callback_data="adm_channels")],
    ]
    if q:
        await q.answer()
        await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════
# ⚙️  تنظیمات ربات — همه از پنل
# ═══════════════════════════════════════════════════════════════
async def adm_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    rows = await get_all_settings()

    # group by group_name
    groups = {}
    for r in rows:
        groups.setdefault(r[3], []).append(r)

    group_emojis = {"آموزشگاه": "🏫", "پرداخت": "💳", "کانال": "📢", "سیستم": "⚙️"}

    text = "⚙️ <b>تنظیمات ربات</b>\n────────────────\n"
    kb = []
    for group, items in groups.items():
        emoji = group_emojis.get(group, "📌")
        text += f"\n{emoji} <b>{group}</b>\n"
        for item in items:
            text += f"  • {item[2]}: <code>{item[1][:30]}</code>\n"
            kb.append([Btn(f"✏️ {item[2]}", callback_data=f"adm_setedit_{item[0]}")])

    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_setting_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key = q.data.replace("adm_setedit_", "")
    rows = await get_all_settings()
    row  = next((r for r in rows if r[0] == key), None)
    if not row:
        return
    context.user_data["edit_setting_key"]   = key
    context.user_data["edit_setting_label"] = row[2]
    context.user_data["state"] = ST_AWAIT_EDIT_SETTING
    await q.edit_message_text(
        f"⚙️ <b>ویرایش: {row[2]}</b>\n\n"
        f"مقدار فعلی:\n<code>{row[1]}</code>\n\n"
        f"مقدار جدید را بنویسید:",
        parse_mode=ParseMode.HTML
    )


async def adm_receive_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_EDIT_SETTING:
        return
    if not is_admin(update.effective_user.id):
        return
    key   = context.user_data.get("edit_setting_key")
    label = context.user_data.get("edit_setting_label", key)
    val   = update.message.text.strip()
    context.user_data["state"] = ST_IDLE
    await set_setting(key, val)
    await update.message.reply_text(
        f"✅ «{label}» ذخیره شد.",
        reply_markup=Kb([[Btn("🔙 بازگشت به تنظیمات", callback_data="adm_settings")]])
    )


# ═══════════════════════════════════════════════════════════════
# ✏️  متون ربات — همه از پنل
# ═══════════════════════════════════════════════════════════════
async def adm_texts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    texts = await get_all_texts()
    kb    = [[Btn(f"✏️ {t[2] or t[0]}", callback_data=f"adm_textedit_{t[0]}")] for t in texts]
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text(
        "✏️ <b>ویرایش متون ربات</b>\nروی هر متن کلیک کنید تا ویرایش کنید:",
        reply_markup=Kb(kb), parse_mode=ParseMode.HTML
    )


async def adm_text_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    key   = q.data.replace("adm_textedit_", "")
    texts = await get_all_texts()
    row   = next((t for t in texts if t[0] == key), None)
    if not row:
        return
    context.user_data["edit_text_key"] = key
    context.user_data["state"] = ST_AWAIT_EDIT_TEXT
    await q.edit_message_text(
        f"✏️ <b>{row[2] or key}</b>\n\n"
        f"متن فعلی:\n<code>{row[1][:600]}</code>\n\n"
        f"متن جدید را بنویسید:\n"
        f"<i>متغیرهایی مثل {{name}} {{school}} {{amount}} را دست نزنید</i>",
        parse_mode=ParseMode.HTML
    )


async def adm_receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_EDIT_TEXT:
        return
    if not is_admin(update.effective_user.id):
        return
    key = context.user_data.get("edit_text_key")
    context.user_data["state"] = ST_IDLE
    await set_text(key, update.message.text)
    await update.message.reply_text(
        "✅ متن ذخیره شد.",
        reply_markup=Kb([[Btn("🔙 بازگشت به متون", callback_data="adm_texts")]])
    )


# ═══════════════════════════════════════════════════════════════
# 📚  جزوات
# ═══════════════════════════════════════════════════════════════
async def adm_prods(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT p.id,p.title,p.price,p.is_active,p.sold_count "
            "FROM products p ORDER BY p.id DESC LIMIT 30"
        ) as c:
            prods = await c.fetchall()

    kb = [[Btn("➕ افزودن جزوه جدید", callback_data="adm_addprod")]]
    for p in prods:
        s = "✅" if p[3] else "❌"
        kb.append([Btn(f"{s} {p[1][:30]} | {fmt(p[2])}ت | {p[4]}🛒", callback_data=f"adm_prod_{p[0]}")])
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text("📚 <b>مدیریت جزوات</b>", reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_prod_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[-1])
    context.user_data["adm_pid"] = pid

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT p.title,p.description,p.price,p.is_active,p.file_type,p.sold_count,c.name "
            "FROM products p LEFT JOIN categories c ON p.category_id=c.id WHERE p.id=?", (pid,)
        ) as c:
            p = await c.fetchone()

    if not p:
        await q.answer("یافت نشد", show_alert=True)
        return

    text = (f"📗 <b>{p[0]}</b>\n"
            f"📝 {p[1] or '—'}\n"
            f"💰 {fmt(p[2])} ت | 📂 {p[6] or '—'} | 📄 {p[4] or '—'}\n"
            f"🛒 فروش: {p[5]} | وضعیت: {'✅ فعال' if p[3] else '❌ غیرفعال'}")
    tgl = "❌ غیرفعال کردن" if p[3] else "✅ فعال کردن"
    kb  = [
        [Btn("✏️ عنوان",  callback_data=f"adm_eprod_title_{pid}"),
         Btn("✏️ قیمت",   callback_data=f"adm_eprod_price_{pid}")],
        [Btn("✏️ توضیح",  callback_data=f"adm_eprod_desc_{pid}"),
         Btn("📎 فایل",   callback_data=f"adm_eprod_file_{pid}")],
        [Btn("📂 دسته",   callback_data=f"adm_eprod_cat_{pid}"),
         Btn(tgl,          callback_data=f"adm_tprod_{pid}")],
        [Btn("🗑️ حذف",   callback_data=f"adm_dprod_{pid}"),
         Btn("🔙 بازگشت", callback_data="adm_prods")],
    ]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_addprod_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["state"]   = ST_AWAIT_PROD_FILE
    context.user_data["newprod"] = {}
    context.user_data["editing_existing"] = False
    await q.edit_message_text("📎 فایل جزوه را ارسال کنید:\n(PDF, Word, PowerPoint, Excel, تصویر)")


async def adm_recv_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_PROD_FILE:
        return
    if not is_admin(update.effective_user.id):
        return
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ لطفاً فایل ارسال کنید.")
        return
    context.user_data["newprod"]["file_id"]   = doc.file_id
    context.user_data["newprod"]["file_name"]  = doc.file_name
    context.user_data["newprod"]["file_type"]  = file_ext(doc.file_name)
    context.user_data["state"] = ST_AWAIT_PROD_TITLE
    await update.message.reply_text("✅ فایل دریافت شد.\n\nعنوان جزوه را وارد کنید:")


async def adm_recv_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_PROD_TITLE:
        return
    if not is_admin(update.effective_user.id):
        return
    val = update.message.text.strip()
    if context.user_data.get("editing_existing"):
        pid = context.user_data.get("adm_pid")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE products SET title=? WHERE id=?", (val, pid))
            await db.commit()
        context.user_data["state"] = ST_IDLE
        await update.message.reply_text("✅ عنوان ویرایش شد.")
        return
    context.user_data["newprod"]["title"] = val
    context.user_data["state"] = ST_AWAIT_PROD_DESC
    await update.message.reply_text("توضیح جزوه (یا /skip):")


async def adm_recv_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_PROD_DESC:
        return
    if not is_admin(update.effective_user.id):
        return
    val = update.message.text.strip()
    if context.user_data.get("editing_existing"):
        pid = context.user_data.get("adm_pid")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE products SET description=? WHERE id=?", (val, pid))
            await db.commit()
        context.user_data["state"] = ST_IDLE
        await update.message.reply_text("✅ توضیح ویرایش شد.")
        return
    context.user_data["newprod"]["description"] = "" if val == "/skip" else val
    context.user_data["state"] = ST_AWAIT_PROD_PRICE
    await update.message.reply_text("قیمت (تومان):")


async def adm_recv_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_PROD_PRICE:
        return
    if not is_admin(update.effective_user.id):
        return
    try:
        val = int(update.message.text.strip().replace(",","").replace("،",""))
    except:
        await update.message.reply_text("❌ عدد صحیح وارد کنید.")
        return
    if context.user_data.get("editing_existing"):
        pid = context.user_data.get("adm_pid")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE products SET price=? WHERE id=?", (val, pid))
            await db.commit()
        context.user_data["state"] = ST_IDLE
        await update.message.reply_text(f"✅ قیمت به {fmt(val)} تومان تغییر کرد.")
        return
    context.user_data["newprod"]["price"] = val
    context.user_data["state"] = ST_AWAIT_PROD_CAT
    await _ask_cat_kb(update.message)


async def _ask_cat_kb(msg):
    """اول پایه رو نشون بده، بعد کاربر پایه رو انتخاب کنه دسته‌بندی‌های اون بیاد"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,emoji,name FROM grades WHERE is_active=1 ORDER BY sort_order,id") as c:
            grades = await c.fetchall()
    if not grades:
        kb = [[Btn("➕ بدون پایه/دسته", callback_data="adm_pcat_0")]]
        await msg.reply_text("⚠️ پایه‌ای وجود ندارد. ابتدا پایه بسازید.", reply_markup=Kb(kb))
        return
    kb = [[Btn(f"{g[1]} {g[2]}", callback_data=f"adm_pgrade_{g[0]}") for g in pair]
           for pair in [grades[i:i+2] for i in range(0, len(grades), 2)]]
    kb.append([Btn("➕ بدون دسته‌بندی", callback_data="adm_pcat_0")])
    await msg.reply_text("🎓 جزوه برای کدام پایه است؟", reply_markup=Kb(kb))


async def adm_set_prod_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid  = int(q.data.split("_")[-1])
    cat  = cid if cid != 0 else None

    if context.user_data.get("editing_existing"):
        pid = context.user_data.get("adm_pid")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE products SET category_id=? WHERE id=?", (cat, pid))
            await db.commit()
        context.user_data["state"] = ST_IDLE
        await q.edit_message_text("✅ دسته‌بندی تغییر کرد.")
        return

    np = context.user_data.get("newprod", {})
    np["category_id"] = cat
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO products(title,description,price,file_id,file_name,file_type,category_id) VALUES(?,?,?,?,?,?,?)",
            (np["title"], np.get("description",""), np["price"], np["file_id"], np.get("file_name",""), np.get("file_type",""), cat)
        )
        await db.commit()
    context.user_data.pop("newprod", None)
    context.user_data["state"] = ST_IDLE
    await q.edit_message_text(f"✅ جزوه «{np['title']}» اضافه شد!")


async def adm_select_prod_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وقتی ادمین پایه رو برای جزوه انتخاب کرد، دسته‌بندی‌های اون پایه رو نشون بده"""
    q = update.callback_query
    await q.answer()
    gid = int(q.data.split("_")[-1])
    context.user_data["newprod_grade"] = gid

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id,emoji,name FROM categories WHERE grade_id=? AND is_active=1 ORDER BY name", (gid,)
        ) as c:
            cats = await c.fetchall()
        async with db.execute("SELECT name,emoji FROM grades WHERE id=?", (gid,)) as c:
            g = await c.fetchone()

    grade_name = f"{g[1]} {g[0]}" if g else ""
    if not cats:
        await q.edit_message_text(
            f"❌ هیچ دسته‌بندی‌ای برای {grade_name} وجود ندارد. ابتدا درس اضافه کنید.",
            reply_markup=Kb([[Btn("🔙 انتخاب پایه دیگر", callback_data="adm_repick_grade")]])
        )
        return

    kb = [[Btn(f"{c[1]} {c[2]}", callback_data=f"adm_pcat_{c[0]}")] for c in cats]
    kb.append([Btn("🔙 تغییر پایه", callback_data="adm_repick_grade")])
    await q.edit_message_text(
        f"{grade_name}\n📖 درس/دسته\u200c\u0628\u0646\u062f\u06cc را انتخاب کنید:",
        reply_markup=Kb(kb)
    )


async def adm_repick_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """برگشت به انتخاب پایه"""
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,emoji,name FROM grades WHERE is_active=1 ORDER BY sort_order,id") as c:
            grades = await c.fetchall()
    kb = [[Btn(f"{g[1]} {g[2]}", callback_data=f"adm_pgrade_{g[0]}") for g in pair]
           for pair in [grades[i:i+2] for i in range(0, len(grades), 2)]]
    kb.append([Btn("➕ بدون دسته‌بندی", callback_data="adm_pcat_0")])
    await q.edit_message_text("🎓 جزوه برای کدام پایه است؟", reply_markup=Kb(kb))


async def adm_toggle_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE products SET is_active=1-is_active WHERE id=?", (pid,))
        await db.commit()
    context.user_data["adm_pid"] = pid
    q.data = f"adm_prod_{pid}"
    await adm_prod_detail(update, context)


async def adm_del_prod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM products WHERE id=?", (pid,))
        await db.commit()
    await q.edit_message_text("✅ جزوه حذف شد.", reply_markup=Kb([[Btn("🔙 بازگشت", callback_data="adm_prods")]]))


async def adm_edit_prod_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")  # adm_eprod_FIELD_PID
    field = parts[2]
    pid   = int(parts[3])
    context.user_data["adm_pid"] = pid
    context.user_data["editing_existing"] = True

    if field == "title":
        context.user_data["state"] = ST_AWAIT_PROD_TITLE
        await q.edit_message_text("عنوان جدید:")
    elif field == "price":
        context.user_data["state"] = ST_AWAIT_PROD_PRICE
        await q.edit_message_text("قیمت جدید (تومان):")
    elif field == "desc":
        context.user_data["state"] = ST_AWAIT_PROD_DESC
        await q.edit_message_text("توضیح جدید:")
    elif field == "file":
        context.user_data["state"] = ST_AWAIT_PROD_FILE
        await q.edit_message_text("📎 فایل جدید را ارسال کنید:")
    elif field == "cat":
        context.user_data["state"] = ST_AWAIT_PROD_CAT
        await _ask_cat_kb(q.message)


async def adm_recv_replace_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_PROD_FILE:
        return
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("editing_existing"):
        await adm_recv_file(update, context)
        return
    doc = update.message.document
    if not doc:
        await update.message.reply_text("❌ فایل ارسال کنید.")
        return
    pid = context.user_data.get("adm_pid")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE products SET file_id=?,file_name=?,file_type=? WHERE id=?",
            (doc.file_id, doc.file_name, file_ext(doc.file_name), pid)
        )
        await db.commit()
    context.user_data["state"] = ST_IDLE
    await update.message.reply_text("✅ فایل جایگزین شد.")


# ═══════════════════════════════════════════════════════════════
# 📂  دسته‌بندی‌ها
# ═══════════════════════════════════════════════════════════════
async def adm_cats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,emoji,name,is_active FROM categories ORDER BY sort_order,name") as c:
            cats = await c.fetchall()
    kb = [[Btn("➕ افزودن دسته‌بندی", callback_data="adm_addcat")]]
    for cat in cats:
        s = "✅" if cat[3] else "❌"
        kb.append([Btn(f"{s} {cat[1]} {cat[2]}", callback_data=f"adm_tcat_{cat[0]}")])
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text("📂 <b>دسته‌بندی‌ها</b>", reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_addcat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # اگه از صفحه grade_cats آمدیم، grade_id رو داریم — مستقیم برو به نام
    if q.data.startswith("adm_addcat_") and q.data != "adm_addcat":
        gid = int(q.data.split("_")[-1])
        context.user_data["new_cat_grade"] = gid
        context.user_data["state"] = ST_AWAIT_CAT_NAME
        await q.edit_message_text("نام درس را وارد کنید:\n(مثال: 📐 ریاضی)")
        return
    # اگه از منوی دسته‌بندی‌ها آمدیم — اول پایه بپرس
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,emoji,name FROM grades WHERE is_active=1 ORDER BY sort_order,id") as c:
            grades = await c.fetchall()
    if not grades:
        await q.edit_message_text(
            "❌ ابتدا باید پایه بسازید.\n\nبه بخش 🎓 پایه‌ها بروید.",
            reply_markup=Kb([[Btn("🎓 رفتن به پایه‌ها", callback_data="adm_grades")]])
        )
        return
    kb = [[Btn(f"{g[1]} {g[2]}", callback_data=f"adm_addcat_{g[0]}") for g in pair]
           for pair in [grades[i:i+2] for i in range(0, len(grades), 2)]]
    kb.append([Btn("🔙 لغو", callback_data="adm_cats")])
    await q.edit_message_text(
        "📂 این درس برای کدام پایه است؟",
        reply_markup=Kb(kb)
    )


async def adm_recv_cat_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_CAT_NAME:
        return
    if not is_admin(update.effective_user.id):
        return
    name  = update.message.text.strip()
    emoji = "📂"
    if name and _is_emoji(name[0]):
        emoji = name[0]
        name  = name[1:].strip()
    gid = context.user_data.get("new_cat_grade")  # None اگه بدون پایه باشه
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO categories(name,emoji,grade_id) VALUES(?,?,?)", (name, emoji, gid))
        await db.commit()
    context.user_data["state"] = ST_IDLE
    back_cb = f"adm_grade_cats_{gid}" if gid else "adm_cats"
    await update.message.reply_text(
        f"✅ درس «{emoji} {name}» اضافه شد.",
        reply_markup=Kb([[Btn("🔙 بازگشت", callback_data=back_cb)]])
    )


async def adm_toggle_cat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE categories SET is_active=1-is_active WHERE id=?", (cid,))
        await db.commit()
    await adm_cats(update, context)


# ═══════════════════════════════════════════════════════════════
# 👥  کاربران
# ═══════════════════════════════════════════════════════════════
async def adm_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT tg_id,full_name,username,wallet,is_banned FROM users ORDER BY joined_at DESC LIMIT 25"
        ) as c:
            users = await c.fetchall()
        async with db.execute("SELECT COUNT(*) FROM users") as c:
            total = (await c.fetchone())[0]

    kb = []
    for u in users:
        b  = "🚫" if u[4] else ""
        kb.append([Btn(f"{b} {u[1][:20]} | @{u[2] or '-'} | 💰{fmt(u[3])}", callback_data=f"adm_user_{u[0]}")])
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text(f"👥 <b>کاربران ({total} نفر)</b>", reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_user_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = int(q.data.split("_")[-1])
    context.user_data["adm_target"] = tid

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT full_name,username,phone,joined_at,wallet,is_banned FROM users WHERE tg_id=?", (tid,)
        ) as c:
            u = await c.fetchone()
        async with db.execute(
            "SELECT COUNT(*),SUM(total_amount) FROM orders WHERE user_id=? AND status='approved'", (tid,)
        ) as c:
            s = await c.fetchone()

    if not u:
        await q.answer("یافت نشد", show_alert=True)
        return

    text = (f"👤 <b>{u[0]}</b>\n@{u[1] or '—'} | {u[2] or '—'}\n"
            f"📅 {u[3][:10]} | 👛 {fmt(u[4])} ت\n"
            f"📦 {s[0]} خرید | {fmt(s[1] or 0)} ت\n"
            f"{'🚫 مسدود' if u[5] else '✅ فعال'}")
    tgl = "✅ رفع مسدودیت" if u[5] else "🚫 مسدود کردن"
    kb  = [
        [Btn(tgl, callback_data=f"adm_ban_{tid}"),
         Btn("💰 شارژ کیف‌پول", callback_data=f"adm_wallet_{tid}")],
        [Btn("🔙 بازگشت", callback_data="adm_users")],
    ]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_banned=1-is_banned WHERE tg_id=?", (tid,))
        await db.commit()
        async with db.execute(
            "SELECT full_name,username,phone,joined_at,wallet,is_banned FROM users WHERE tg_id=?", (tid,)
        ) as c:
            u = await c.fetchone()
        async with db.execute(
            "SELECT COUNT(*),SUM(total_amount) FROM orders WHERE user_id=? AND status='approved'", (tid,)
        ) as c:
            s = await c.fetchone()

    if not u:
        await q.answer("یافت نشد", show_alert=True)
        return

    text = (f"👤 <b>{u[0]}</b>\n@{u[1] or '—'} | {u[2] or '—'}\n"
            f"📅 {u[3][:10]} | 👛 {fmt(u[4])} ت\n"
            f"📦 {s[0]} خرید | {fmt(s[1] or 0)} ت\n"
            f"{'🚫 مسدود' if u[5] else '✅ فعال'}")
    tgl = "✅ رفع مسدودیت" if u[5] else "🚫 مسدود کردن"
    kb  = [
        [Btn(tgl, callback_data=f"adm_ban_{tid}"),
         Btn("💰 شارژ کیف‌پول", callback_data=f"adm_wallet_{tid}")],
        [Btn("🔙 بازگشت", callback_data="adm_users")],
    ]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_wallet_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["adm_target"] = int(q.data.split("_")[-1])
    context.user_data["state"] = ST_AWAIT_WALLET_AMT
    await q.edit_message_text("مبلغ شارژ کیف‌پول (تومان):")


async def adm_recv_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_WALLET_AMT:
        return
    if not is_admin(update.effective_user.id):
        return
    try:
        amount = int(update.message.text.strip().replace(",","").replace("،",""))
    except:
        await update.message.reply_text("❌ عدد صحیح وارد کنید.")
        return
    tid = context.user_data.get("adm_target")
    context.user_data["state"] = ST_IDLE
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET wallet=wallet+? WHERE tg_id=?", (amount, tid))
        await db.execute("INSERT INTO wallet_transactions(user_id,amount,type,description) VALUES(?,?,'credit','شارژ توسط ادمین')", (tid, amount))
        await db.commit()
    await context.bot.send_message(tid, f"💰 {fmt(amount)} تومان به کیف‌پول شما اضافه شد!")
    await update.message.reply_text(f"✅ {fmt(amount)} تومان شارژ شد.")


# ═══════════════════════════════════════════════════════════════
# 📦  سفارشات
# ═══════════════════════════════════════════════════════════════
async def adm_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT o.id,u.full_name,o.total_amount,o.status,o.created_at "
            "FROM orders o JOIN users u ON o.user_id=u.tg_id ORDER BY o.id DESC LIMIT 25"
        ) as c:
            orders = await c.fetchall()

    sm = {"pending":"⏳","approved":"✅","rejected":"❌"}
    kb = []
    for o in orders:
        kb.append([Btn(f"{sm.get(o[3],'❓')} #{o[0]} | {o[1][:15]} | {fmt(o[2])}ت", callback_data=f"adm_order_{o[0]}")])
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text("📦 <b>سفارشات</b>", reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_order_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    oid = int(q.data.split("_")[-1])

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT o.id,u.full_name,u.tg_id,o.total_amount,o.discount_amount,o.status,o.created_at,o.reject_reason "
            "FROM orders o JOIN users u ON o.user_id=u.tg_id WHERE o.id=?", (oid,)
        ) as c:
            o = await c.fetchone()
        async with db.execute(
            "SELECT p.title,oi.price FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (oid,)
        ) as c:
            items = await c.fetchall()

    sm = {"pending":"⏳ در انتظار","approved":"✅ تأیید شده","rejected":"❌ رد شده"}
    text = (f"📦 سفارش #{o[0]}\n"
            f"👤 {o[1]} | {o[2]}\n"
            f"📅 {o[6][:16]}\n"
            f"💰 {fmt(o[3])} ت (تخفیف: {fmt(o[4])} ت)\n"
            f"وضعیت: {sm.get(o[5],o[5])}\n")
    if o[7]:
        text += f"دلیل رد: {o[7]}\n"
    text += "\nآیتم‌ها:\n" + "\n".join(f"• {i[0]} — {fmt(i[1])} ت" for i in items)

    kb = [[Btn("🔙 بازگشت", callback_data="adm_orders")]]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════
# 🎟️  کدهای تخفیف
# ═══════════════════════════════════════════════════════════════
async def adm_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,code,type,value,max_uses,used_count,is_active,per_user FROM coupons ORDER BY id DESC") as c:
            coupons = await c.fetchall()

    kb = [[Btn("➕ کد تخفیف جدید", callback_data="adm_addcoup")]]
    for c in coupons:
        s    = "✅" if c[6] else "❌"
        val  = f"{c[3]}%" if c[2]=="percent" else f"{fmt(c[3])}ت"
        uses = f"{c[5]}/{c[4]}" if c[4]>0 else f"{c[5]}/∞"
        pu   = f"هر نفر: {'∞' if c[7]==0 else c[7]}بار"
        kb.append([Btn(f"{s} {c[1]} | {val} | {uses} | {pu}", callback_data=f"adm_tcoup_{c[0]}")])
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text("🎟️ <b>کدهای تخفیف</b>", reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_addcoup_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["state"] = ST_AWAIT_COUP_CODE
    context.user_data["newcoup"] = {}
    await q.edit_message_text("کد تخفیف را وارد کنید (انگلیسی بزرگ):")


async def adm_recv_coup_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_COUP_CODE:
        return
    if not is_admin(update.effective_user.id):
        return
    context.user_data["newcoup"]["code"] = update.message.text.strip().upper()
    context.user_data["state"] = ST_AWAIT_COUP_TYPE
    kb = [[Btn("درصدی (%)", callback_data="adm_couptyp_percent")],
          [Btn("مبلغ ثابت", callback_data="adm_couptyp_fixed")]]
    await update.message.reply_text("نوع تخفیف:", reply_markup=Kb(kb))


async def adm_coup_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["newcoup"]["type"] = q.data.split("_")[-1]
    context.user_data["state"] = ST_AWAIT_COUP_VALUE
    label = "درصد (۱-۱۰۰):" if context.user_data["newcoup"]["type"]=="percent" else "مبلغ (تومان):"
    await q.edit_message_text(label)


async def adm_recv_coup_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_COUP_VALUE:
        return
    if not is_admin(update.effective_user.id):
        return
    try:
        context.user_data["newcoup"]["value"] = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ عدد صحیح وارد کنید.")
        return
    context.user_data["state"] = ST_AWAIT_COUP_MAX
    await update.message.reply_text("حداکثر استفاده (۰=بی‌نهایت):")


async def adm_recv_coup_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_COUP_MAX:
        return
    if not is_admin(update.effective_user.id):
        return
    try:
        mx = int(update.message.text.strip())
    except:
        mx = 0
    context.user_data["newcoup"]["max_uses"] = mx
    context.user_data["state"] = ST_AWAIT_COUP_PER_USER
    await update.message.reply_text(
        "هر کاربر چند بار می‌تواند از این کد استفاده کند؟\n(۱ = یک بار، ۰ = بی‌نهایت)"
    )


async def adm_recv_coup_per_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_COUP_PER_USER:
        return
    if not is_admin(update.effective_user.id):
        return
    try:
        per_user = int(update.message.text.strip())
    except:
        per_user = 1
    nc = context.user_data["newcoup"]
    mx = nc.get("max_uses", 0)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO coupons(code,type,value,max_uses,per_user) VALUES(?,?,?,?,?)",
            (nc["code"], nc["type"], nc["value"], mx, per_user)
        )
        await db.commit()
    context.user_data.pop("newcoup", None)
    context.user_data["state"] = ST_IDLE
    val_text = f"{nc['value']}%" if nc['type'] == 'percent' else f"{fmt(nc['value'])} تومان"
    max_text = 'بی\u200cنهایت' if mx == 0 else str(mx)
    msg = (
        "\u2705 \u06a9\u062f \u062a\u062e\u0641\u06cc\u0641 \u0633\u0627\u062e\u062a\u0647 \u0634\u062f!\n\n"
        f"\U0001f39f\ufe0f \u06a9\u062f: <code>{nc['code']}</code>\n"
        f"\U0001f4b0 \u0645\u0642\u062f\u0627\u0631: {val_text}\n"
        f"\U0001f522 \u062d\u062f\u0627\u06a9\u062b\u0631 \u0627\u0633\u062a\u0641\u0627\u062f\u0647: {max_text}\n\n"
        "\u0627\u06cc\u0646 \u06a9\u062f \u0631\u0627 \u06a9\u067e\u06cc \u06a9\u0646\u06cc\u062f \u0648 \u0628\u0647 \u06a9\u0627\u0631\u0628\u0631\u0627\u0646 \u0628\u062f\u0647\u06cc\u062f."
    )
    await update.message.reply_text(msg, parse_mode="HTML",
        reply_markup=Kb([[Btn("🔙 بازگشت", callback_data="adm_coupons")]])
    )


async def adm_toggle_coup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE coupons SET is_active=1-is_active WHERE id=?", (cid,))
        await db.commit()
    await adm_coupons(update, context)


# ═══════════════════════════════════════════════════════════════
# 📊  آمار
# ═══════════════════════════════════════════════════════════════
async def adm_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*),SUM(total_amount) FROM orders WHERE status='approved'") as c:
            total = await c.fetchone()
        async with db.execute(
            "SELECT COUNT(*),SUM(total_amount) FROM orders WHERE status='approved' AND date(created_at)=date('now')"
        ) as c:
            today = await c.fetchone()
        async with db.execute(
            "SELECT COUNT(*),SUM(total_amount) FROM orders WHERE status='approved' AND created_at>=date('now','-30 days')"
        ) as c:
            month = await c.fetchone()
        async with db.execute(
            "SELECT p.title,COUNT(oi.id) FROM order_items oi JOIN products p ON oi.product_id=p.id "
            "JOIN orders o ON oi.order_id=o.id WHERE o.status='approved' "
            "GROUP BY oi.product_id ORDER BY COUNT(oi.id) DESC LIMIT 5"
        ) as c:
            top = await c.fetchall()
        async with db.execute("SELECT COUNT(*) FROM users WHERE date(joined_at)=date('now')") as c:
            new_users = (await c.fetchone())[0]

    text = (f"📊 <b>آمار فروش</b>\n────────────────\n"
            f"📅 امروز: {today[0]} سفارش | {fmt(today[1] or 0)} ت\n"
            f"📆 این ماه: {month[0]} سفارش | {fmt(month[1] or 0)} ت\n"
            f"📈 کل: {total[0]} سفارش | {fmt(total[1] or 0)} ت\n"
            f"👤 کاربر جدید امروز: {new_users}\n"
            f"────────────────\n⭐ پرفروش‌ترین:\n")
    for i, t in enumerate(top, 1):
        text += f"{i}. {t[0][:30]} ({t[1]} فروش)\n"

    kb = [[Btn("🔙 پنل ادمین", callback_data="adm_panel")]]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════
# 📢  پیام انبوه
# ═══════════════════════════════════════════════════════════════
async def adm_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["state"] = ST_AWAIT_BROADCAST
    await q.edit_message_text("📢 پیام خود را بنویسید (متن، عکس، ویدیو):\n/cancel برای لغو")


async def adm_send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_BROADCAST:
        return
    if not is_admin(update.effective_user.id):
        return
    if update.message.text == "/cancel":
        context.user_data["state"] = ST_IDLE
        await update.message.reply_text("❌ لغو شد.")
        return
    context.user_data["state"] = ST_IDLE

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT tg_id FROM users WHERE is_banned=0") as c:
            users = await c.fetchall()

    sent = failed = 0
    sm = await update.message.reply_text(f"⏳ در حال ارسال به {len(users)} نفر...")
    for u in users:
        try:
            await update.message.copy(u[0])
            sent += 1
        except:
            failed += 1

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO broadcasts(text,sent_count) VALUES(?,?)",
                         (update.message.text or "[media]", sent))
        await db.commit()

    await sm.edit_text(f"✅ ارسال به {sent} نفر | ❌ ناموفق: {failed}")


# ═══════════════════════════════════════════════════════════════
# 👛  کیف‌پول‌ها
# ═══════════════════════════════════════════════════════════════
async def adm_wallets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT tg_id,full_name,wallet FROM users WHERE wallet>0 ORDER BY wallet DESC LIMIT 20"
        ) as c:
            users = await c.fetchall()

    kb = [[Btn(f"{u[1][:20]} | {fmt(u[2])} ت", callback_data=f"adm_wallet_{u[0]}")] for u in users]
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text("👛 <b>کیف‌پول کاربران</b>", reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


# ═══════════════════════════════════════════════════════════════
# 🎓  مدیریت پایه‌ها
# ═══════════════════════════════════════════════════════════════
async def adm_grades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,emoji,name,is_active FROM grades ORDER BY sort_order,id") as c:
            grades = await c.fetchall()
    kb = [[Btn("➕ افزودن پایه جدید", callback_data="adm_addgrade")]]
    for g in grades:
        s = "✅" if g[3] else "❌"
        kb.append([
            Btn(f"{s} {g[1]} {g[2]}", callback_data=f"adm_grade_{g[0]}"),
        ])
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])
    await q.edit_message_text("🎓 <b>مدیریت پایه‌ها</b>", reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_grade_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.split("_")[-1])
    context.user_data["adm_gid"] = gid
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name,emoji,is_active FROM grades WHERE id=?", (gid,)) as c:
            g = await c.fetchone()
        async with db.execute("SELECT COUNT(*) FROM categories WHERE grade_id=?", (gid,)) as c:
            cat_count = (await c.fetchone())[0]
    if not g:
        await q.answer("یافت نشد", show_alert=True)
        return
    text = (f"🎓 <b>{g[1]} {g[0]}</b>\n"
            f"📂 تعداد دسته‌بندی: {cat_count}\n"
            f"وضعیت: {'✅ فعال' if g[2] else '❌ غیرفعال'}")
    tgl = "❌ غیرفعال" if g[2] else "✅ فعال کردن"
    kb = [
        [Btn("📂 دسته‌بندی‌های این پایه", callback_data=f"adm_grade_cats_{gid}")],
        [Btn(tgl, callback_data=f"adm_tgrade_{gid}"),
         Btn("🗑️ حذف", callback_data=f"adm_dgrade_{gid}")],
        [Btn("🔙 بازگشت", callback_data="adm_grades")],
    ]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_addgrade_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["state"] = ST_AWAIT_GRADE_NAME
    await q.edit_message_text("🎓 نام پایه را وارد کنید:\n(مثال: 🔟 دهم   یا   📚 کنکور)")


async def adm_recv_grade_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_GRADE_NAME:
        return
    if not is_admin(update.effective_user.id):
        return
    name  = update.message.text.strip()
    emoji = "🎓"
    if name and _is_emoji(name[0]):
        emoji = name[0]
        name  = name[1:].strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO grades(name,emoji) VALUES(?,?)", (name, emoji))
        await db.commit()
    context.user_data["state"] = ST_IDLE
    await update.message.reply_text(
        f"✅ پایه «{emoji} {name}» اضافه شد!",
        reply_markup=Kb([[Btn("🔙 بازگشت به پایه‌ها", callback_data="adm_grades")]])
    )


async def adm_toggle_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE grades SET is_active=1-is_active WHERE id=?", (gid,))
        await db.commit()
    context.user_data["adm_gid"] = gid
    # به جای q.data مستقیم اطلاعات پایه رو نمایش می‌دیم
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name,emoji,is_active FROM grades WHERE id=?", (gid,)) as c:
            g = await c.fetchone()
        async with db.execute("SELECT COUNT(*) FROM categories WHERE grade_id=?", (gid,)) as c:
            cat_count = (await c.fetchone())[0]
    if not g:
        await q.answer("یافت نشد", show_alert=True)
        return
    text = (f"🎓 <b>{g[1]} {g[0]}</b>\n"
            f"📂 تعداد دسته‌بندی: {cat_count}\n"
            f"وضعیت: {'✅ فعال' if g[2] else '❌ غیرفعال'}")
    tgl = "❌ غیرفعال" if g[2] else "✅ فعال کردن"
    kb = [
        [Btn("📂 دسته‌بندی‌های این پایه", callback_data=f"adm_grade_cats_{gid}")],
        [Btn(tgl, callback_data=f"adm_tgrade_{gid}"),
         Btn("🗑️ حذف", callback_data=f"adm_dgrade_{gid}")],
        [Btn("🔙 بازگشت", callback_data="adm_grades")],
    ]
    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def adm_del_grade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM grades WHERE id=?", (gid,))
        await db.commit()
    await q.edit_message_text("✅ پایه حذف شد.", reply_markup=Kb([[Btn("🔙 بازگشت", callback_data="adm_grades")]]))


# دسته‌بندی‌های یک پایه خاص
async def adm_grade_cats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    gid = int(q.data.split("_")[-1])
    context.user_data["adm_gid"] = gid
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name,emoji FROM grades WHERE id=?", (gid,)) as c:
            g = await c.fetchone()
        async with db.execute(
            "SELECT id,emoji,name,is_active FROM categories WHERE grade_id=? ORDER BY sort_order,name", (gid,)
        ) as c:
            cats = await c.fetchall()
    grade_name = f"{g[1]} {g[0]}" if g else "این پایه"
    kb = [[Btn(f"➕ افزودن درس به {grade_name}", callback_data=f"adm_addcat_{gid}")]]
    for cat in cats:
        s = "✅" if cat[3] else "❌"
        kb.append([Btn(f"{s} {cat[1]} {cat[2]}", callback_data=f"adm_tcat_{cat[0]}")])
    kb.append([Btn("🔙 بازگشت به پایه", callback_data=f"adm_grade_{gid}")])
    await q.edit_message_text(
        f"📂 دسته‌بندی‌های {grade_name}:",
        reply_markup=Kb(kb), parse_mode=ParseMode.HTML
    )


# ═══════════════════════════════════════════════════════════════
# 📢  مدیریت کانال‌های عضویت اجباری
# ═══════════════════════════════════════════════════════════════
async def adm_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id,channel_id,channel_name,is_active FROM join_channels") as c:
            channels = await c.fetchall()

    active_setting = await get_setting("join_channels_active","1")
    status = "✅ فعال" if active_setting == "1" else "❌ غیرفعال"

    kb = [
        [Btn(f"وضعیت عضویت اجباری: {status}", callback_data="adm_toggle_join")],
        [Btn("➕ افزودن کانال", callback_data="adm_addchannel")],
    ]
    for ch in channels:
        s = "✅" if ch[3] else "❌"
        kb.append([Btn(f"{s} {ch[2]} ({ch[1]})", callback_data=f"adm_delchannel_{ch[0]}")])
    kb.append([Btn("🔙 پنل ادمین", callback_data="adm_panel")])

    await q.edit_message_text(
        "📢 <b>کانال‌های عضویت اجباری</b>\n\n"
        "برای حذف کانال روی آن کلیک کنید.",
        reply_markup=Kb(kb), parse_mode=ParseMode.HTML
    )


async def adm_toggle_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    current = await get_setting("join_channels_active","1")
    await set_setting("join_channels_active", "0" if current=="1" else "1")
    await adm_channels(update, context)


async def adm_addchannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    context.user_data["state"] = ST_AWAIT_CHANNEL_INFO
    await q.edit_message_text(
        "📢 آیدی کانال را وارد کنید:\n\n"
        "مثال: @mychannel\n\n"
        "⚠️ ربات باید ادمین کانال باشد."
    )


async def adm_recv_channel_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_CHANNEL_INFO:
        return
    if not is_admin(update.effective_user.id):
        return
    context.user_data["state"] = ST_IDLE
    text = update.message.text.strip()
    ch_id = text.strip()
    if not ch_id:
        await update.message.reply_text("❌ آیدی کانال را وارد کنید.\nمثال: @mychannel")
        return
    # نام کانال رو از تلگرام بگیر
    try:
        chat_id = int(ch_id) if ch_id.lstrip('-').isdigit() else ch_id
        chat = await context.bot.get_chat(chat_id)
        ch_name = chat.title or ch_id
    except:
        ch_name = ch_id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO join_channels(channel_id,channel_name) VALUES(?,?)",
            (ch_id, ch_name)
        )
        await db.commit()
    await update.message.reply_text(
        f"✅ کانال «{ch_name}» ({ch_id}) اضافه شد!",
        reply_markup=Kb([[Btn("🔙 بازگشت به کانال‌ها", callback_data="adm_channels")]])
    )


async def adm_del_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try: await q.answer()
    except: pass
    cid = int(q.data.split("_")[-1])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM join_channels WHERE id=?", (cid,))
        await db.commit()
    await adm_channels(update, context)