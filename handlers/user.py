import os
import aiosqlite
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb
from telegram import ReplyKeyboardMarkup as RKb, KeyboardButton as KBtn
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from database.db import DB_PATH, get_text, get_setting
from config.config import *
from utils.helpers import fmt, gen_ref_code, now_str, file_ext, chunks


# ─── دکمه بازگشت شیشه‌ای ─────────────────────────────────────────────────────
def back_btn(callback: str, label: str = "◀️ بازگشت") -> list:
    """یک ردیف دکمه بازگشت شیشه‌ای برمی‌گردونه"""
    return [Btn(label, callback_data=callback)]


async def _btns() -> dict:
    """لود همه متن دکمه‌ها از دیتابیس"""
    keys = ["btn_back","btn_main","btn_add_cart","btn_buy_now","btn_cart",
            "btn_checkout","btn_clear_cart","btn_orders","btn_products",
            "btn_profile","btn_referral","btn_reject","btn_approve",
            "btn_skip_coupon","btn_support","btn_use_coupon","btn_wallet",
            "btn_redownload","btn_use_wallet"]
    result = {}
    for k in keys:
        result[k] = await get_text(k)
    return result


async def ensure_user(update: Update):
    u = update.effective_user
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users WHERE tg_id=?", (u.id,)) as c:
            row = await c.fetchone()
        if not row:
            await db.execute(
                "INSERT OR IGNORE INTO users(tg_id,username,full_name,referral_code) VALUES(?,?,?,?)",
                (u.id, u.username or "", u.full_name or "", gen_ref_code())
            )
            await db.commit()


# ─── منوی ثابت پایین ─────────────────────────────────────────────────────────
async def get_reply_keyboard(uid: int) -> RKb:
    rows = [[KBtn("📋 منو")]]
    if is_admin(uid): rows.append([KBtn("⚙️ پنل مدیریت")])
    return RKb(rows, resize_keyboard=True)


# ─── START ───────────────────────────────────────────────────────────────────
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ensure_user(update)
    u = update.effective_user

    if context.args and context.args[0].startswith("ref_"):
        code = context.args[0][4:]
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT tg_id FROM users WHERE referral_code=?", (code,)) as c:
                ref = await c.fetchone()
            if ref and ref[0] != u.id:
                await db.execute(
                    "UPDATE users SET referred_by=? WHERE tg_id=? AND referred_by IS NULL",
                    (ref[0], u.id)
                )
                await db.commit()

    if await get_setting("bot_active","1") != "1" and not is_admin(u.id):
        await update.message.reply_text(await get_text("bot_inactive"))
        return

    # ۱. چک عضویت اجباری (ادمین معاف)
    if not is_admin(u.id):
        from handlers.registration import check_join, send_join_required, is_profile_done, start_registration
        ok, not_joined = await check_join(context, u.id)
        if not ok:
            await send_join_required(update.message, context, not_joined)
            return
        # ۲. چک پروفایل
        if not await is_profile_done(u.id):
            await start_registration(update.message, context, u.id)
            return

    await send_main_menu(update, context)


async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u      = update.effective_user
    school = await get_setting("school_name", "آموزشگاه")
    text   = await get_text("welcome", name=u.first_name, school=school)
    rk     = await get_reply_keyboard(u.id)
    if update.callback_query:
        await update.callback_query.answer()
        # برای بازگشت از صفحات داخلی، منوی inline رو نشون بده
        wallet_on   = await get_setting("wallet_enabled",   "1") == "1"
        referral_on = await get_setting("referral_enabled", "1") == "1"
        kb = [
            [Btn(await get_text("btn_products"), callback_data="grades")],
            [Btn(await get_text("btn_cart"),     callback_data="cart"),
             Btn(await get_text("btn_orders"),   callback_data="my_orders")],
            [Btn(await get_text("btn_profile"),  callback_data="profile"),
             Btn(await get_text("btn_support"),  callback_data="support")],
        ]
        extra = []
        if wallet_on:   extra.append(Btn(await get_text("btn_wallet"),   callback_data="wallet"))
        if referral_on: extra.append(Btn(await get_text("btn_referral"), callback_data="referral"))
        if extra: kb.append(extra)
        kb.append([Btn("ℹ️ درباره ما", callback_data="about")])
        await update.callback_query.edit_message_text(
            f"📋 منوی {school}:",
            reply_markup=Kb(kb)
        )
    else:
        await update.message.reply_text(text, reply_markup=rk, parse_mode=ParseMode.HTML)


# ─── ROUTER برای دکمه‌های ثابت ───────────────────────────────────────────────
async def reply_kb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        return False
    text = update.message.text.strip()
    uid  = update.effective_user.id
    if text == "📋 منو":
        await _send_inline_menu(update, context)
    elif text == "⚙️ پنل مدیریت" and is_admin(uid):
        from handlers.admin import admin_panel
        await admin_panel(update, context)
    else:
        return False
    return True


# ═══════════════════════════════════════════════════════════════
# فلوی خرید: پایه ← دسته‌بندی ← جزوه
# ═══════════════════════════════════════════════════════════════

# ─── GRADES (پایه) ───────────────────────────────────────────────────────────
async def _send_inline_menu(update, context):
    uid = update.effective_user.id
    wallet_on   = await get_setting("wallet_enabled",   "1") == "1"
    referral_on = await get_setting("referral_enabled", "1") == "1"

    school = await get_setting("school_name", "آموزشگاه")
    kb = [
        [Btn(await get_text("btn_products"), callback_data="grades")],
        [Btn(await get_text("btn_cart"),     callback_data="cart"),
         Btn(await get_text("btn_orders"),   callback_data="my_orders")],
        [Btn(await get_text("btn_profile"),  callback_data="profile"),
         Btn(await get_text("btn_support"),  callback_data="support")],
    ]
    extra = []
    if wallet_on:   extra.append(Btn(await get_text("btn_wallet"),   callback_data="wallet"))
    if referral_on: extra.append(Btn(await get_text("btn_referral"), callback_data="referral"))
    if extra: kb.append(extra)
    kb.append([Btn("ℹ️ درباره ما", callback_data="about")])

    await update.message.reply_text(
        f"📋 منوی {school}:",
        reply_markup=Kb(kb)
    )


async def show_grades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await _send_grades(update, context, via_callback=True)


async def _send_grades(update, context, via_callback=False):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id,emoji,name FROM grades WHERE is_active=1 ORDER BY sort_order,id"
        ) as c:
            grades = await c.fetchall()

    if not grades:
        txt = "❌ هیچ پایه‌ای تعریف نشده.\nلطفاً با ادمین تماس بگیرید."
        if via_callback:
            await update.callback_query.edit_message_text(txt)
        else:
            await update.message.reply_text(txt)
        return

    rows = [[Btn(f"{g[1]} {g[2]}", callback_data=f"grade_{g[0]}") for g in pair]
             for pair in chunks(grades, 2)]
    rows.append([back_btn("main_menu", "◀️ بازگشت به منو")[0]])
    txt = "📚 پایه تحصیلی خود را انتخاب کنید:"
    if via_callback:
        await update.callback_query.edit_message_text(txt, reply_markup=Kb(rows))
    else:
        await update.message.reply_text(txt, reply_markup=Kb(rows))


# ─── CATEGORIES (دسته‌بندی/درس) ──────────────────────────────────────────────
async def show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    grade_id = int(q.data.split("_")[1])
    context.user_data["cur_grade"] = grade_id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT name,emoji FROM grades WHERE id=?", (grade_id,)) as c:
            g = await c.fetchone()
        async with db.execute(
            "SELECT id,emoji,name FROM categories WHERE grade_id=? AND is_active=1 ORDER BY sort_order,name",
            (grade_id,)
        ) as c:
            cats = await c.fetchall()

    if not cats:
        await q.edit_message_text(
            f"❌ هیچ درسی برای {g[1] if g else ''} {g[0] if g else 'این پایه'} ثبت نشده.",
            reply_markup=Kb([[back_btn("grades", "◀️ بازگشت به پایه‌ها")[0]]])
        )
        return

    grade_name = f"{g[1]} {g[0]}" if g else ""
    rows = [[Btn(f"{cat[1]} {cat[2]}", callback_data=f"cat_{cat[0]}") for cat in pair]
             for pair in chunks(cats, 2)]
    rows.append([back_btn("grades", "◀️ بازگشت به پایه‌ها")[0]])
    await q.edit_message_text(
        f"{grade_name}\n📖 درس مورد نظر را انتخاب کنید:",
        reply_markup=Kb(rows)
    )


# ─── PRODUCTS (جزوات) ─────────────────────────────────────────────────────────
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cat_id = int(q.data.split("_")[1])
    context.user_data["cur_cat"] = cat_id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT c.name,c.emoji,g.name,g.emoji FROM categories c LEFT JOIN grades g ON c.grade_id=g.id WHERE c.id=?",
            (cat_id,)
        ) as c:
            meta = await c.fetchone()
        async with db.execute(
            "SELECT id,title,price FROM products WHERE category_id=? AND is_active=1 ORDER BY title",
            (cat_id,)
        ) as c:
            prods = await c.fetchall()

    grade_id = context.user_data.get("cur_grade", 0)
    if not prods:
        await q.edit_message_text(
            await get_text("no_products"),
            reply_markup=Kb([[back_btn(f"grade_{grade_id}", "◀️ بازگشت به دسته‌بندی‌ها")[0]]])
        )
        return

    header = ""
    if meta:
        header = f"{meta[3] or ''} {meta[2] or ''} | {meta[1] or ''} {meta[0] or ''}\n"
    rows = [[Btn(f"📗 {p[1][:35]} — {fmt(p[2])} ت", callback_data=f"prod_{p[0]}")] for p in prods]
    rows.append([back_btn(f"grade_{grade_id}", "◀️ بازگشت به دسته‌بندی‌ها")[0]])
    await q.edit_message_text(
        header + await get_text("choose_product"),
        reply_markup=Kb(rows)
    )


# ─── PRODUCT DETAIL ──────────────────────────────────────────────────────────
async def product_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[1])
    context.user_data["cur_prod"] = pid

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT p.title,p.description,p.price,p.file_type,p.sold_count,c.name,g.name "
            "FROM products p "
            "LEFT JOIN categories c ON p.category_id=c.id "
            "LEFT JOIN grades g ON c.grade_id=g.id "
            "WHERE p.id=?", (pid,)
        ) as c:
            p = await c.fetchone()
        async with db.execute(
            "SELECT AVG(stars),COUNT(*) FROM ratings WHERE product_id=?", (pid,)
        ) as c:
            rat = await c.fetchone()
        uid = update.effective_user.id
        async with db.execute(
            "SELECT oi.id FROM order_items oi JOIN orders o ON oi.order_id=o.id "
            "WHERE o.user_id=? AND oi.product_id=? AND o.status='approved'", (uid, pid)
        ) as c:
            bought = await c.fetchone()

    if not p:
        await q.answer("یافت نشد", show_alert=True)
        return

    stars = f"{rat[0]:.1f}⭐ ({rat[1]} نظر)" if rat[0] else "بدون امتیاز"
    text  = (f"📗 <b>{p[0]}</b>\n────────────────\n"
             f"📝 {p[1] or '—'}\n"
             f"🎓 پایه: {p[6] or '—'} | 📖 درس: {p[5] or '—'}\n"
             f"📄 فرمت: {p[3] or '—'}\n"
             f"🛒 فروش: {p[4]} | ⭐ {stars}\n"
             f"💰 قیمت: <b>{fmt(p[2])} تومان</b>")

    cat = context.user_data.get("cur_cat", 0)
    if bought:
        text += "\n\n✅ <i>قبلاً خریداری کرده‌اید</i>"
        kb = [[Btn(await get_text("btn_redownload"), callback_data=f"redownload_prod_{pid}")],
              [back_btn(f"cat_{cat}", "◀️ بازگشت به جزوات")[0]]]
    else:
        kb = [[Btn(await get_text("btn_add_cart"), callback_data=f"addcart_{pid}"),
               Btn(await get_text("btn_buy_now"),  callback_data=f"buynow_{pid}")],
              [back_btn(f"cat_{cat}", "◀️ بازگشت به جزوات")[0]]]

    await q.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


# ─── CART ────────────────────────────────────────────────────────────────────
async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    pid = int(q.data.split("_")[1])
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT oi.id FROM order_items oi JOIN orders o ON oi.order_id=o.id "
            "WHERE o.user_id=? AND oi.product_id=? AND o.status='approved'", (uid, pid)
        ) as c:
            if await c.fetchone():
                await q.answer(await get_text("product_already_bought"), show_alert=True)
                return
        try:
            await db.execute("INSERT INTO cart_items(user_id,product_id) VALUES(?,?)", (uid, pid))
            await db.commit()
            await q.answer(await get_text("product_added_cart"), show_alert=True)
        except:
            await q.answer(await get_text("product_already_cart"), show_alert=True)


async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await _send_cart(update, context, via_callback=bool(update.callback_query))


async def _send_cart(update, context, via_callback=False):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT p.id,p.title,p.price FROM cart_items ci "
            "JOIN products p ON ci.product_id=p.id WHERE ci.user_id=?", (uid,)
        ) as c:
            items = await c.fetchall()

    if not items:
        txt = await get_text("cart_empty")
        kb  = Kb([[Btn(await get_text("btn_products"), callback_data="grades")],
                  [back_btn("main_menu", "◀️ بازگشت به منو")[0]]])
        if via_callback:
            await update.callback_query.edit_message_text(txt, reply_markup=kb)
        else:
            await update.message.reply_text(txt, reply_markup=kb)
        return

    total = sum(i[2] for i in items)
    text  = await get_text("cart_header") + "\n"
    for i in items:
        text += f"\n📗 {i[1]} — {fmt(i[2])} ت"
    text += f"\n────────────────\n💰 جمع: <b>{fmt(total)} تومان</b>"
    kb = [[Btn(await get_text("btn_checkout"),   callback_data="checkout")],
          [Btn(await get_text("btn_clear_cart"), callback_data="clear_cart"),
           Btn(await get_text("btn_products"),   callback_data="grades")],
          [back_btn("main_menu", "◀️ بازگشت به منو")[0]]]
    if via_callback:
        await update.callback_query.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM cart_items WHERE user_id=?", (update.effective_user.id,))
        await db.commit()
    await q.edit_message_text("🗑️ سبد خرید پاک شد.",
        reply_markup=Kb([[Btn(await get_text("btn_products"), callback_data="grades")],
                         [back_btn("main_menu", "◀️ بازگشت به منو")[0]]]))


# ─── CHECKOUT ────────────────────────────────────────────────────────────────
async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    if q.data.startswith("buynow_"):
        pid = int(q.data.split("_")[1])
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM cart_items WHERE user_id=?", (uid,))
            await db.execute("INSERT OR IGNORE INTO cart_items(user_id,product_id) VALUES(?,?)", (uid, pid))
            await db.commit()
    context.user_data["discount"]    = 0
    context.user_data["coupon"]      = None
    context.user_data["wallet_used"] = 0
    kb = [[Btn(await get_text("btn_use_coupon"),  callback_data="enter_coupon")],
          [Btn(await get_text("btn_skip_coupon"), callback_data="skip_coupon")],
          [back_btn("cart", "◀️ بازگشت به سبد خرید")[0]]]
    await q.edit_message_text(await get_text("coupon_ask"), reply_markup=Kb(kb))


async def enter_coupon_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["state"] = ST_AWAIT_COUPON
    await q.edit_message_text(await get_text("coupon_enter"))


async def skip_coupon_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await _show_payment(q, update.effective_user.id, context)


async def process_coupon_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip().upper()
    uid  = update.effective_user.id
    context.user_data["state"] = ST_IDLE
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id,type,value,max_uses,used_count,per_user FROM coupons "
            "WHERE code=? AND is_active=1 AND (expires_at IS NULL OR expires_at>datetime('now'))", (code,)
        ) as c:
            coup = await c.fetchone()
    if not coup:
        await update.message.reply_text(await get_text("coupon_invalid"))
        return
    # چک تعداد کل استفاده
    if coup[3] > 0 and coup[4] >= coup[3]:
        await update.message.reply_text(await get_text("coupon_invalid"))
        return
    # چک تعداد استفاده هر کاربر
    per_user = coup[5] if coup[5] else 1
    if per_user > 0:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM orders WHERE user_id=? AND coupon_code=? AND status IN ('approved','pending')",
                (uid, code)
            ) as c:
                user_used = (await c.fetchone())[0]
        if user_used >= per_user:
            await update.message.reply_text("❌ شما قبلاً از این کد تخفیف استفاده کرده‌اید.")
            return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT SUM(p.price) FROM cart_items ci JOIN products p ON ci.product_id=p.id WHERE ci.user_id=?", (uid,)
        ) as c:
            total = (await c.fetchone())[0] or 0
    disc = int(total * coup[2] / 100) if coup[1] == "percent" else coup[2]
    context.user_data["discount"]  = disc
    context.user_data["coupon"]    = code
    context.user_data["coupon_id"] = coup[0]
    await update.message.reply_text(await get_text("coupon_valid", discount=fmt(disc)))

    class FQ:
        def __init__(s, m): s.message = m
        async def answer(s): pass
        async def edit_message_text(s, *a, **kw): await s.message.reply_text(*a, **kw)
    await _show_payment(FQ(update.message), uid, context)


async def _show_payment(q, uid, context):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT p.id,p.title,p.price FROM cart_items ci "
            "JOIN products p ON ci.product_id=p.id WHERE ci.user_id=?", (uid,)
        ) as c:
            items = await c.fetchall()
        async with db.execute("SELECT wallet FROM users WHERE tg_id=?", (uid,)) as c:
            u = await c.fetchone()
    wallet = u[0] if u else 0
    disc   = context.user_data.get("discount", 0)
    total  = sum(i[2] for i in items)
    final  = max(0, total - disc)
    context.user_data["cart_items"] = items
    context.user_data["total"]      = total
    context.user_data["final"]      = final
    bank  = await get_setting("bank_card",  "—")
    owner = await get_setting("bank_owner", "—")
    bname = await get_setting("bank_name",  "—")
    lines = ""
    for i in items:
        lines += f"\n📗 {i[1]} — {fmt(i[2])} ت"
    if disc:
        lines += f"\n🎟️ تخفیف: -{fmt(disc)} ت"
    lines += f"\n────────────────\n💰 مبلغ نهایی: <b>{fmt(final)} تومان</b>\n\n"
    lines += await get_text("payment_info", bank=bname, card=bank, owner=owner, amount=fmt(final))
    kb = []
    if wallet > 0 and await get_setting("wallet_enabled", "1") == "1":
        use = min(wallet, final)
        kb.append([Btn(f"{await get_text('btn_use_wallet')} ({fmt(use)} ت)", callback_data="use_wallet")])
    kb.append([back_btn("cart", "◀️ بازگشت به سبد خرید")[0]])
    context.user_data["state"] = ST_AWAIT_RECEIPT
    await q.edit_message_text(lines, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def use_wallet_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT wallet FROM users WHERE tg_id=?", (uid,)) as c:
            u = await c.fetchone()
    wallet = u[0] if u else 0
    final  = context.user_data.get("final", 0)
    use    = min(wallet, final)
    context.user_data["wallet_used"] = use
    context.user_data["final"]       = final - use
    await q.answer(await get_text("wallet_used", amount=fmt(use)), show_alert=True)
    await _show_payment(q, uid, context)


# ─── RECEIVE RECEIPT ─────────────────────────────────────────────────────────
async def receive_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_RECEIPT:
        return
    # فقط عکس قبول می‌شه (معمولی یا فشرده‌شده/document تصویری)
    is_photo = bool(update.message.photo)
    is_image_doc = (update.message.document and
                    update.message.document.mime_type and
                    update.message.document.mime_type.startswith("image/"))
    if not is_photo and not is_image_doc:
        await update.message.reply_text("❌ لطفاً فقط عکس رسید را ارسال کنید.")
        return
    u     = update.effective_user
    uid   = u.id
    items = context.user_data.get("cart_items", [])
    final = context.user_data.get("final", 0)
    disc  = context.user_data.get("discount", 0)
    coupon= context.user_data.get("coupon")
    w_use = context.user_data.get("wallet_used", 0)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO orders(user_id,total_amount,discount_amount,coupon_code,status) VALUES(?,?,?,?,'pending')",
            (uid, final, disc, coupon)
        )
        oid = cur.lastrowid
        for item in items:
            await db.execute("INSERT INTO order_items(order_id,product_id,price) VALUES(?,?,?)",
                             (oid, item[0], item[2]))
        if w_use:
            await db.execute("UPDATE users SET wallet=wallet-? WHERE tg_id=?", (w_use, uid))
            await db.execute("INSERT INTO wallet_transactions(user_id,amount,type,description) VALUES(?,?,'debit','خرید')", (uid, w_use))
        if coupon:
            await db.execute("UPDATE coupons SET used_count=used_count+1 WHERE code=?", (coupon,))
        await db.execute("DELETE FROM cart_items WHERE user_id=?", (uid,))
        await db.commit()
    channel = await get_setting("receipt_channel", "")
    if channel:
        ch_text = await get_text("channel_msg",
            name=u.full_name or u.first_name,
            username=u.username or "ندارد",
            user_id=uid, amount=fmt(final),
            order_id=oid, item_count=len(items), time=now_str()
        )
        ch_kb = Kb([[Btn(await get_text("btn_approve"), callback_data=f"approve_{oid}_{uid}"),
                     Btn(await get_text("btn_reject"),  callback_data=f"reject_{oid}_{uid}")]])
        try:
            if update.message.photo:
                await context.bot.send_photo(channel, update.message.photo[-1].file_id,
                    caption=ch_text, reply_markup=ch_kb, parse_mode=ParseMode.HTML)
            elif is_image_doc:
                await context.bot.send_document(channel, update.message.document.file_id,
                    caption=ch_text, reply_markup=ch_kb, parse_mode=ParseMode.HTML)
        except:
            pass
    context.user_data["state"] = ST_IDLE
    await update.message.reply_text(await get_text("receipt_sent", order_id=oid), parse_mode=ParseMode.HTML)


# ─── APPROVE / REJECT ────────────────────────────────────────────────────────
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, oid, uid = q.data.split("_")
    oid, uid = int(oid), int(uid)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status='approved',paid_at=datetime('now','localtime') WHERE id=?", (oid,))
        await db.commit()
        async with db.execute(
            "SELECT oi.product_id,p.file_id,p.file_name,p.file_type,p.title "
            "FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (oid,)
        ) as c:
            items = await c.fetchall()
        async with db.execute("SELECT full_name,phone,first_last_name,national_id FROM users WHERE tg_id=?", (uid,)) as c:
            urow = await c.fetchone()
        async with db.execute("SELECT referred_by FROM users WHERE tg_id=?", (uid,)) as c:
            ref_row = await c.fetchone()
    if ref_row and ref_row[0]:
        reward = int(await get_setting("referral_reward", "10000"))
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET wallet=wallet+? WHERE tg_id=?", (reward, ref_row[0]))
            await db.execute("INSERT INTO referral_rewards(referrer_id,referred_id,reward) VALUES(?,?,?)", (ref_row[0], uid, reward))
            await db.execute("INSERT INTO wallet_transactions(user_id,amount,type,description) VALUES(?,?,'credit','پاداش معرف')", (ref_row[0], reward))
            await db.execute("UPDATE users SET referred_by=NULL WHERE tg_id=?", (uid,))
            await db.commit()
        await context.bot.send_message(ref_row[0], await get_text("referral_reward_msg", amount=fmt(reward)))
    suffix = f"\n\n✅ تأیید شد — {q.from_user.first_name}"
    try:
        if q.message.caption:
            await q.edit_message_caption(q.message.caption + suffix, reply_markup=None)
        else:
            await q.edit_message_text(q.message.text + suffix, reply_markup=None)
    except:
        pass
    await context.bot.send_message(uid, await get_text("order_approved", order_id=oid), parse_mode=ParseMode.HTML)
    await _send_watermarked_files(context, uid, items, urow)
    await context.bot.send_message(uid, await get_text("watermark_done"), parse_mode=ParseMode.HTML)
    async with aiosqlite.connect(DB_PATH) as db:
        for item in items:
            await db.execute("UPDATE products SET sold_count=sold_count+1 WHERE id=?", (item[0],))
        await db.commit()
    if await get_setting("rating_enabled", "1") == "1":
        await _ask_rating(context, uid, oid)


async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, oid, uid = q.data.split("_")
    admin_id = q.from_user.id
    # ذخیره اطلاعات پیام کانال برای ویرایش بعدی
    context.user_data[f"rej_{admin_id}"] = (int(oid), int(uid), q.message)
    context.user_data["state"] = ST_AWAIT_REJECT_REASON
    await context.bot.send_message(admin_id, "📝 دلیل رد را بنویسید:")


async def process_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != ST_AWAIT_REJECT_REASON:
        return
    reason  = update.message.text.strip()
    key     = f"rej_{update.effective_user.id}"
    stored  = context.user_data.get(key, (None, None, None))
    oid, target, ch_msg = stored
    context.user_data["state"] = ST_IDLE
    if not oid:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE orders SET status='rejected',reject_reason=? WHERE id=?", (reason, oid))
        await db.commit()
    # ویرایش پیام کانال — دکمه‌ها حذف و متن رد اضافه میشه
    suffix = f"\n\n❌ رد شد — {update.effective_user.first_name}\n📝 دلیل: {reason}"
    try:
        if ch_msg:
            if ch_msg.caption:
                await ch_msg.edit_caption(ch_msg.caption + suffix, reply_markup=None)
            else:
                await ch_msg.edit_text(ch_msg.text + suffix, reply_markup=None)
    except:
        pass
    await context.bot.send_message(target, await get_text("order_rejected", reason=reason), parse_mode=ParseMode.HTML)
    await update.message.reply_text(f"✅ سفارش #{oid} رد شد.")


# ─── SEND WATERMARKED FILES (با protect_content) ─────────────────────────────
async def _send_watermarked_files(context, uid, items, urow):
    from utils.watermark import apply_watermark
    # urow: full_name, phone, first_last_name, national_id
    user_name   = (urow[2] or urow[0]) if urow else str(uid)
    phone       = urow[1] if urow and urow[1] else "—"
    national_id = urow[3] if urow and len(urow) > 3 and urow[3] else ""
    school      = await get_setting("school_name", "آموزشگاه")
    for item in items:
        pid, fid, fname, ftype, title = item
        if not fid:
            continue
        try:
            ext     = ftype or file_ext(fname or "file.bin")
            orig    = f"temp/{uid}_{pid}_orig.{ext}"
            wm_path = f"temp/{uid}_{pid}_wm.{ext}"
            tg_file = await context.bot.get_file(fid)
            await tg_file.download_to_drive(orig)
            await apply_watermark(orig, ext, user_name, phone, school, wm_path, national_id)
            with open(wm_path, "rb") as f:
                # ✅ protect_content=True — جلوگیری از forward و download
                await context.bot.send_document(
                    uid, f,
                    filename=f"{title}.{ext}",
                    protect_content=True
                )
            os.remove(orig)
            os.remove(wm_path)
        except Exception as e:
            await context.bot.send_message(uid, f"⚠️ خطا در ارسال: {title}\n{e}")


# ─── RATING ──────────────────────────────────────────────────────────────────
async def _ask_rating(context, uid, oid):
    kb = [
        [Btn("1 ⭐",     callback_data=f"rate_{oid}_1")],
        [Btn("2 ⭐⭐",   callback_data=f"rate_{oid}_2")],
        [Btn("3 ⭐⭐⭐", callback_data=f"rate_{oid}_3")],
        [Btn("4 ⭐⭐⭐⭐",callback_data=f"rate_{oid}_4")],
        [Btn("5 ⭐⭐⭐⭐⭐",callback_data=f"rate_{oid}_5")],
    ]
    await context.bot.send_message(uid, await get_text("rating_ask"), reply_markup=Kb(kb))


async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split("_")
    oid, stars = int(parts[1]), int(parts[2])
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT product_id FROM order_items WHERE order_id=? LIMIT 1", (oid,)) as c:
            row = await c.fetchone()
        if row:
            await db.execute(
                "INSERT OR REPLACE INTO ratings(user_id,order_id,product_id,stars) VALUES(?,?,?,?)",
                (uid, oid, row[0], stars)
            )
            await db.commit()
    await q.edit_message_text(await get_text("rating_done"))


# ─── MY ORDERS ───────────────────────────────────────────────────────────────
async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await _send_orders(update, context, via_callback=bool(update.callback_query))


async def _send_orders(update, context, via_callback=False):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id,total_amount,status,created_at FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,)
        ) as c:
            orders = await c.fetchall()
    sm = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
    if not orders:
        txt = "📦 هنوز سفارشی ثبت نشده."
        kb  = Kb([[back_btn("main_menu", "◀️ بازگشت به منو")[0]]])
        if via_callback:
            await update.callback_query.edit_message_text(txt, reply_markup=kb)
        else:
            await update.message.reply_text(txt, reply_markup=kb)
        return
    text = "📦 <b>سفارشات شما</b>\n────────────────\n"
    kb   = []
    for o in orders:
        text += f"\n{sm.get(o[2],'❓')} #{o[0]} | {fmt(o[1])} ت | {o[3][:10]}"
        if o[2] == "approved":
            kb.append([Btn(f"📥 دانلود مجدد #{o[0]}", callback_data=f"redownload_{o[0]}")])
    kb.append([back_btn("main_menu", "◀️ بازگشت به منو")[0]])
    if via_callback:
        await update.callback_query.edit_message_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=Kb(kb), parse_mode=ParseMode.HTML)


async def redownload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    oid = int(q.data.split("_")[1])
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT oi.product_id,p.file_id,p.file_name,p.file_type,p.title "
            "FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (oid,)
        ) as c:
            items = await c.fetchall()
        async with db.execute("SELECT full_name,phone,first_last_name,national_id FROM users WHERE tg_id=?", (uid,)) as c:
            urow = await c.fetchone()
    await q.edit_message_text(await get_text("redownload_ready", order_id=oid))
    await _send_watermarked_files(context, uid, items, urow)


async def redownload_prod(update, context):
    q = update.callback_query
    await q.answer()
    pid = int(q.data.split("_")[-1])
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT oi.order_id FROM order_items oi JOIN orders o ON oi.order_id=o.id "
            "WHERE o.user_id=? AND oi.product_id=? AND o.status='approved' LIMIT 1", (uid, pid)
        ) as c:
            row = await c.fetchone()
        if not row:
            await q.edit_message_text("❌ سفارشی یافت نشد.")
            return
        oid = row[0]
        async with db.execute(
            "SELECT oi.product_id,p.file_id,p.file_name,p.file_type,p.title "
            "FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?", (oid,)
        ) as c:
            items = await c.fetchall()
        async with db.execute("SELECT full_name,phone,first_last_name,national_id FROM users WHERE tg_id=?", (uid,)) as c:
            urow = await c.fetchone()
    await q.edit_message_text(await get_text("redownload_ready", order_id=oid))
    await _send_watermarked_files(context, uid, items, urow)


# ─── PROFILE ─────────────────────────────────────────────────────────────────
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await _send_profile(update, context, via_callback=bool(update.callback_query))


async def _send_profile(update, context, via_callback=False):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT full_name,username,phone,joined_at,wallet,first_last_name,national_id,city,grade FROM users WHERE tg_id=?", (uid,)
        ) as c:
            u = await c.fetchone()
        async with db.execute(
            "SELECT COUNT(*),SUM(total_amount) FROM orders WHERE user_id=? AND status='approved'", (uid,)
        ) as c:
            s = await c.fetchone()
    text = (f"👤 <b>{u[5] or u[0]}</b>\n"
            f"🪪 کد ملی: {u[6] or '—'}\n"
            f"📱 موبایل: {u[2] or '—'}\n"
            f"🏙️ شهر: {u[7] or '—'} | 🎓 پایه: {u[8] or '—'}\n"
            f"📅 عضویت: {u[3][:10]}\n"
            f"👛 کیف‌پول: {fmt(u[4])} ت\n"
            f"📦 خریدها: {s[0]} | {fmt(s[1] or 0)} ت")
    kb = Kb([[Btn("✏️ ویرایش اطلاعات", callback_data="edit_profile")],
             [back_btn("main_menu", "◀️ بازگشت به منو")[0]]])
    if via_callback:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ─── WALLET ──────────────────────────────────────────────────────────────────
async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await _send_wallet(update, context, via_callback=bool(update.callback_query))


async def _send_wallet(update, context, via_callback=False):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT wallet FROM users WHERE tg_id=?", (uid,)) as c:
            u = await c.fetchone()
        async with db.execute(
            "SELECT amount,type,description,created_at FROM wallet_transactions "
            "WHERE user_id=? ORDER BY created_at DESC LIMIT 8", (uid,)
        ) as c:
            txs = await c.fetchall()
    bal  = u[0] if u else 0
    text = await get_text("wallet_info", balance=fmt(bal)) + "\n────────────────\n"
    for tx in txs:
        sign = "+" if tx[1] == "credit" else "-"
        text += f"{sign}{fmt(abs(tx[0]))} ت — {tx[2]} ({tx[3][:10]})\n"
    kb = Kb([[back_btn("main_menu", "◀️ بازگشت به منو")[0]]])
    if via_callback:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ─── REFERRAL ────────────────────────────────────────────────────────────────
async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await _send_referral(update, context, via_callback=bool(update.callback_query))


async def _send_referral(update, context, via_callback=False):
    uid = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT referral_code FROM users WHERE tg_id=?", (uid,)) as c:
            u = await c.fetchone()
        async with db.execute(
            "SELECT COUNT(*),SUM(reward) FROM referral_rewards WHERE referrer_id=?", (uid,)
        ) as c:
            r = await c.fetchone()
    if not u:
        txt = "❌ خطا: اطلاعات شما یافت نشد. لطفاً /start بزنید."
        if via_callback:
            await update.callback_query.edit_message_text(txt)
        else:
            await update.message.reply_text(txt)
        return
    me     = await context.bot.get_me()
    link   = f"https://t.me/{me.username}?start=ref_{u[0]}"
    reward = await get_setting("referral_reward", "10000")
    text   = await get_text("referral_info", link=link, reward=fmt(int(reward)))
    text  += f"\n\n👥 معرفی‌شده: {r[0]} | 💰 درآمد: {fmt(r[1] or 0)} ت"
    kb = Kb([[back_btn("main_menu", "◀️ بازگشت به منو")[0]]])
    if via_callback:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ─── SUPPORT ─────────────────────────────────────────────────────────────────
async def _send_about(update, context):
    school = await get_setting("school_name", "آموزشگاه")
    text   = await get_text("about_text", school=school)
    if not text or text == "about_text":
        text = f"📚 {school}"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    school = await get_setting("school_name", "آموزشگاه")
    text   = await get_text("about_text", school=school)
    kb = Kb([[back_btn("main_menu", "◀️ بازگشت به منو")[0]]])
    await q.edit_message_text(text or f"📚 {school}", reply_markup=kb, parse_mode=ParseMode.HTML)


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await _send_support(update, context, via_callback=bool(update.callback_query))


async def _send_support(update, context, via_callback=False):
    sup_user  = await get_text("support_username")
    sup_hours = await get_text("support_hours")
    if not sup_user: sup_user = await get_setting("support_username", "@support")
    if not sup_hours: sup_hours = await get_setting("support_hours", "۹ تا ۹")
    text = await get_text("support_msg", username=sup_user, hours=sup_hours)
    kb = Kb([[back_btn("main_menu", "◀️ بازگشت به منو")[0]]])
    if via_callback:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)