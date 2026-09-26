"""
ربات فروش جزوه — نقطهٔ شروع

اجرا:
    pip install -r requirements.txt
    cp .env.example .env      # BOT_TOKEN و ADMIN_IDS را پر کنید
    python bot.py

این فایل فقط مسیریابی را انجام می‌دهد: هر دکمه (callback) و هر پیام را به
هندلر درستش در پوشهٔ handlers می‌فرستد. همهٔ منطق خرید، ثبت‌نام و پنل ادمین
داخل handlers است و همهٔ تنظیمات و متن‌ها از پنل ادمین داخل ربات تغییر می‌کنند.
"""
import logging

from telegram import Update, CallbackQuery
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

from config.config import *  # BOT_TOKEN, ADMIN_IDS, is_admin, ST_*
from database.db import init_db, get_setting, get_text, is_user_banned
from handlers import user as U
from handlers import registration as R
from handlers import admin as A

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("jozveh-bot")


# ─── پاسخ امن به دکمه‌ها ─────────────────────────────────────────────────────
# چند هندلر (مثل تغییر وضعیت و بازگشت به لیست) دو بار به یک دکمه جواب می‌دهند.
# تلگرام بار دوم خطا می‌دهد؛ اینجا آن خطا بی‌صدا نادیده گرفته می‌شود.
_orig_answer = CallbackQuery.answer


async def _safe_answer(self, *args, **kwargs):
    try:
        return await _orig_answer(self, *args, **kwargs)
    except BadRequest as e:
        msg = str(e).lower()
        if "query is too old" in msg or "query id is invalid" in msg or "already" in msg:
            return False
        raise

CallbackQuery.answer = _safe_answer


# ═══════════════════════════════════════════════════════════════
# جدول مسیریابی دکمه‌ها
# ═══════════════════════════════════════════════════════════════
# دکمه‌هایی که دقیقاً همین مقدار را دارند
EXACT_ROUTES = {
    # کاربر
    "main_menu":      U.send_main_menu,
    "grades":         U.show_grades,
    "cart":           U.show_cart,
    "clear_cart":     U.clear_cart,
    "checkout":       U.checkout_start,
    "enter_coupon":   U.enter_coupon_cb,
    "skip_coupon":    U.skip_coupon_cb,
    "use_wallet":     U.use_wallet_cb,
    "my_orders":      U.my_orders,
    "profile":        U.show_profile,
    "wallet":         U.show_wallet,
    "referral":       U.show_referral,
    "support":        U.show_support,
    "about":          U.show_about,
    # ثبت‌نام و پروفایل
    "check_join":     R.handle_check_join,
    "back_provinces": R.handle_back_provinces,
    "edit_profile":   R.show_profile_edit,
    # ادمین
    "adm_panel":        A.admin_panel,
    "adm_settings":     A.adm_settings,
    "adm_texts":        A.adm_texts,
    "adm_prods":        A.adm_prods,
    "adm_addprod":      A.adm_addprod_start,
    "adm_repick_grade": A.adm_repick_grade,
    "adm_cats":         A.adm_cats,
    "adm_addcat":       A.adm_addcat_start,
    "adm_users":        A.adm_users,
    "adm_orders":       A.adm_orders,
    "adm_coupons":      A.adm_coupons,
    "adm_addcoup":      A.adm_addcoup_start,
    "adm_stats":        A.adm_stats,
    "adm_broadcast":    A.adm_broadcast_start,
    "adm_wallets":      A.adm_wallets,
    "adm_grades":       A.adm_grades,
    "adm_addgrade":     A.adm_addgrade_start,
    "adm_channels":     A.adm_channels,
    "adm_toggle_join":  A.adm_toggle_join,
    "adm_addchannel":   A.adm_addchannel_start,
}

# دکمه‌هایی که با یک پیشوند شروع می‌شوند — ترتیب مهم است (پیشوند بلندتر اول)
PREFIX_ROUTES = [
    # کاربر
    ("redownload_prod_", U.redownload_prod),
    ("redownload_",      U.redownload),
    ("grade_",           U.show_categories),
    ("cat_",             U.show_products),
    ("prod_",            U.product_detail),
    ("addcart_",         U.add_to_cart),
    ("buynow_",          U.checkout_start),
    ("rate_",            U.handle_rating),
    # تأیید / رد رسید (در کانال رسیدها)
    ("approve_",         U.approve_payment),
    ("reject_",          U.reject_payment),
    # ثبت‌نام و پروفایل
    ("province_",        R.handle_province_select),
    ("city_",            R.handle_city_select),
    ("edit_prof_",       R.handle_edit_profile_field),
    # ادمین
    ("adm_setedit_",     A.adm_setting_edit),
    ("adm_textedit_",    A.adm_text_edit),
    ("adm_eprod_",       A.adm_edit_prod_field),
    ("adm_tprod_",       A.adm_toggle_prod),
    ("adm_dprod_",       A.adm_del_prod),
    ("adm_prod_",        A.adm_prod_detail),
    ("adm_pgrade_",      A.adm_select_prod_grade),
    ("adm_pcat_",        A.adm_set_prod_cat),
    ("adm_addcat_",      A.adm_addcat_start),
    ("adm_tcat_",        A.adm_toggle_cat),
    ("adm_user_",        A.adm_user_detail),
    ("adm_ban_",         A.adm_ban_user),
    ("adm_wallet_",      A.adm_wallet_start),
    ("adm_order_",       A.adm_order_detail),
    ("adm_couptyp_",     A.adm_coup_type),
    ("adm_tcoup_",       A.adm_toggle_coup),
    ("adm_grade_cats_",  A.adm_grade_cats),
    ("adm_grade_",       A.adm_grade_detail),
    ("adm_tgrade_",      A.adm_toggle_grade),
    ("adm_dgrade_",      A.adm_del_grade),
    ("adm_delchannel_",  A.adm_del_channel),
]

# دکمه‌هایی که فقط ادمین حق زدنشان را دارد
ADMIN_ONLY_PREFIXES = ("adm_", "approve_", "reject_")

# دکمه‌هایی که پیش از کامل شدن ثبت‌نام هم مجازند
PRE_REGISTER_ALLOWED = ("check_join", "province_", "city_", "back_provinces")


def _resolve(data: str):
    if data in EXACT_ROUTES:
        return EXACT_ROUTES[data]
    for prefix, handler in PREFIX_ROUTES:
        if data.startswith(prefix):
            return handler
    return None


# ═══════════════════════════════════════════════════════════════
# نگهبان‌های مشترک
# ═══════════════════════════════════════════════════════════════
async def _blocked(update: Update, uid: int) -> bool:
    """کاربر مسدود یا ربات خاموش؟ (ادمین هیچ‌وقت مسدود نمی‌شود)"""
    if is_admin(uid):
        return False
    if await is_user_banned(uid):
        text = "⛔️ دسترسی شما به ربات مسدود شده است."
    elif await get_setting("bot_active", "1") != "1":
        text = await get_text("bot_inactive") or "⏸ ربات موقتاً غیرفعال است."
    else:
        return False
    if update.callback_query:
        await update.callback_query.answer(text, show_alert=True)
    elif update.effective_message:
        await update.effective_message.reply_text(text)
    return True


# ═══════════════════════════════════════════════════════════════
# دکمه‌ها
# ═══════════════════════════════════════════════════════════════
async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data or ""
    uid  = update.effective_user.id

    if data.startswith(ADMIN_ONLY_PREFIXES) and not is_admin(uid):
        await q.answer("⛔️ این بخش فقط برای ادمین است.", show_alert=True)
        return

    if await _blocked(update, uid):
        return

    handler = _resolve(data)
    if handler is None:
        await q.answer()
        log.warning("Unknown callback: %s", data)
        return

    # هر مسیر دیگری جز ثبت‌نام، پروفایل کامل می‌خواهد
    if (not is_admin(uid)
            and not data.startswith(PRE_REGISTER_ALLOWED)
            and not await R.is_profile_done(uid)):
        await U.ensure_user(update)
        await q.answer()
        await R.start_registration(q.message, context, uid)
        return

    await handler(update, context)


# ═══════════════════════════════════════════════════════════════
# پیام‌ها (متن، عکس، فایل، شماره تماس...)
# ═══════════════════════════════════════════════════════════════
# هر حالت انتظار → هندلر مربوطش
STATE_ROUTES = {
    # کاربر
    ST_AWAIT_RECEIPT:       U.receive_receipt,
    ST_AWAIT_COUPON:        U.process_coupon_text,
    ST_AWAIT_REJECT_REASON: U.process_reject_reason,
    # ادمین
    ST_AWAIT_EDIT_SETTING:  A.adm_receive_setting,
    ST_AWAIT_EDIT_TEXT:     A.adm_receive_text,
    ST_AWAIT_PROD_FILE:     A.adm_recv_replace_file,   # فایل جزوهٔ جدید یا جایگزین
    ST_AWAIT_PROD_TITLE:    A.adm_recv_title,
    ST_AWAIT_PROD_DESC:     A.adm_recv_desc,
    ST_AWAIT_PROD_PRICE:    A.adm_recv_price,
    ST_AWAIT_CAT_NAME:      A.adm_recv_cat_name,
    ST_AWAIT_WALLET_AMT:    A.adm_recv_wallet,
    ST_AWAIT_COUP_CODE:     A.adm_recv_coup_code,
    ST_AWAIT_COUP_VALUE:    A.adm_recv_coup_value,
    ST_AWAIT_COUP_MAX:      A.adm_recv_coup_max,
    ST_AWAIT_COUP_PER_USER: A.adm_recv_coup_per_user,
    ST_AWAIT_BROADCAST:     A.adm_send_broadcast,      # متن، عکس، ویدیو...
    ST_AWAIT_GRADE_NAME:    A.adm_recv_grade_name,
    ST_AWAIT_CHANNEL_INFO:  A.adm_recv_channel_info,
}

# حالت‌هایی که ورودی غیرمتنی قبول می‌کنند
NON_TEXT_STATES = {ST_AWAIT_RECEIPT, ST_AWAIT_PROD_FILE, ST_AWAIT_BROADCAST}


async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or msg.chat.type != "private":
        return
    uid = update.effective_user.id
    if await _blocked(update, uid):
        return
    await U.ensure_user(update)

    # ۱. دکمه‌های ثابت پایین صفحه (📋 منو / ⚙️ پنل مدیریت)
    if msg.text and await U.reply_kb_router(update, context):
        return

    # ۲. مراحل ثبت‌نام و ویرایش پروفایل
    if context.user_data.get("reg_step"):
        if await R.handle_edit_profile_value(update, context):
            return
        if await R.handle_registration(update, context):
            return

    # ۳. کاربری که پروفایلش کامل نیست
    if not is_admin(uid) and not await R.is_profile_done(uid):
        await R.start_registration(msg, context, uid)
        return

    # ۴. حالت‌های انتظار (رسید، کد تخفیف، فرم‌های ادمین...)
    state   = context.user_data.get("state", ST_IDLE)
    handler = STATE_ROUTES.get(state)
    if handler:
        if state not in NON_TEXT_STATES and not msg.text:
            await msg.reply_text("✍️ لطفاً پاسخ را به‌صورت متن بفرستید. (/cancel برای لغو)")
            return
        await handler(update, context)
        return

    # ۵. پیام آزاد — منو را نشان بده
    await U._send_inline_menu(update, context)


# ═══════════════════════════════════════════════════════════════
# دستورها
# ═══════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    uid = update.effective_user.id
    if not is_admin(uid) and await is_user_banned(uid):
        await _blocked(update, uid)
        return
    context.user_data["state"] = ST_IDLE   # هر فرم نیمه‌کاره با /start بسته می‌شود
    await U.start_handler(update, context)  # خاموش بودن ربات را خودش بررسی می‌کند


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        await A.admin_panel(update, context)


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await _blocked(update, update.effective_user.id):
        return
    await U._send_inline_menu(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو هر فرم نیمه‌کاره. در حالت پیام انبوه، خود هندلر پیام «لغو شد» را می‌دهد."""
    if context.user_data.get("state") == ST_AWAIT_BROADCAST:
        await A.adm_send_broadcast(update, context)
        return
    context.user_data["state"] = ST_IDLE
    for key in ("newprod", "newcoup", "editing_existing"):
        context.user_data.pop(key, None)
    if context.user_data.get("reg_step", "") and str(context.user_data["reg_step"]).startswith("edit_"):
        context.user_data["reg_step"] = None
    await update.message.reply_text("❌ لغو شد.", reply_markup=await U.get_reply_keyboard(update.effective_user.id))


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/skip فقط در مرحلهٔ «توضیح جزوه» معنا دارد"""
    if context.user_data.get("state") == ST_AWAIT_PROD_DESC:
        await A.adm_recv_desc(update, context)
    else:
        await update.message.reply_text("این دستور الان کاربردی ندارد.")


# ─── خطاها ───────────────────────────────────────────────────────────────────
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    if isinstance(err, BadRequest) and "message is not modified" in str(err).lower():
        return  # دکمه دوباره زده شده و صفحه تغییری نکرده
    if isinstance(err, Forbidden):
        return  # کاربر ربات را بلاک کرده
    log.exception("Unhandled error", exc_info=err)
    try:
        if isinstance(update, Update) and update.effective_chat and update.effective_chat.type == "private":
            await context.bot.send_message(update.effective_chat.id, "⚠️ خطایی رخ داد. لطفاً دوباره تلاش کنید.")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# راه‌اندازی
# ═══════════════════════════════════════════════════════════════
async def post_init(app: Application):
    await init_db()
    me = await app.bot.get_me()
    log.info("Bot @%s is running | admins: %d", me.username, len([a for a in ADMIN_IDS if a]))


def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN تنظیم نشده. فایل .env را از روی .env.example بسازید.")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .concurrent_updates(False)   # ترتیب پیام‌های هر کاربر حفظ شود (فرم‌های چندمرحله‌ای)
        .build()
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("admin",  cmd_admin))
    app.add_handler(CommandHandler("menu",   cmd_menu))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("skip",   cmd_skip))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, message_router))
    app.add_error_handler(on_error)

    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
