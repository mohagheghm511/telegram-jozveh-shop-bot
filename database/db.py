import aiosqlite
import os

DB_PATH = "database/bot.db"

CREATE_TABLES = """
PRAGMA journal_mode=WAL;

-- تنظیمات کلی ربات (همه از پنل ادمین)
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    label TEXT,
    group_name TEXT DEFAULT 'عمومی'
);

-- متون ربات (همه از پنل ادمین)
CREATE TABLE IF NOT EXISTS bot_texts (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    tg_id         INTEGER UNIQUE NOT NULL,
    username      TEXT,
    full_name     TEXT,
    phone         TEXT,
    joined_at     TEXT DEFAULT (datetime('now','localtime')),
    is_banned       INTEGER DEFAULT 0,
    referral_code   TEXT UNIQUE,
    referred_by     INTEGER,
    wallet          INTEGER DEFAULT 0,
    first_last_name TEXT,
    national_id     TEXT,
    city            TEXT,
    grade           TEXT,
    profile_done    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS grades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    emoji      TEXT DEFAULT '🎓',
    is_active  INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    emoji      TEXT DEFAULT '📂',
    grade_id   INTEGER,
    is_active  INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    FOREIGN KEY(grade_id) REFERENCES grades(id)
);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT,
    category_id INTEGER,
    price       INTEGER NOT NULL,
    file_id     TEXT,
    file_name   TEXT,
    file_type   TEXT,
    is_active   INTEGER DEFAULT 1,
    sold_count  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY(category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS cart_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    added_at   TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(user_id, product_id)
);

CREATE TABLE IF NOT EXISTS orders (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER NOT NULL,
    total_amount      INTEGER NOT NULL,
    discount_amount   INTEGER DEFAULT 0,
    coupon_code       TEXT,
    status            TEXT DEFAULT 'pending',
    receipt_file_id   TEXT,
    channel_message_id INTEGER,
    reject_reason     TEXT,
    created_at        TEXT DEFAULT (datetime('now','localtime')),
    paid_at           TEXT,
    FOREIGN KEY(user_id) REFERENCES users(tg_id)
);

CREATE TABLE IF NOT EXISTS order_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    price      INTEGER NOT NULL,
    FOREIGN KEY(order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS coupons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT UNIQUE NOT NULL,
    type       TEXT NOT NULL,
    value      INTEGER NOT NULL,
    max_uses   INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    expires_at TEXT,
    per_user   INTEGER DEFAULT 1,
    is_active  INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS ratings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    stars      INTEGER NOT NULL,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(user_id, product_id)
);

CREATE TABLE IF NOT EXISTS referral_rewards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    referrer_id INTEGER NOT NULL,
    referred_id INTEGER NOT NULL,
    reward      INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    amount      INTEGER NOT NULL,
    type        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS join_channels (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    is_active    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT,
    sent_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now','localtime'))
);
"""

# تنظیمات پیش‌فرض — همه از پنل ادمین تغییر می‌کنند
DEFAULT_SETTINGS = [
    # گروه: آموزشگاه
    ("school_name",        "آموزشگاه من",         "نام آموزشگاه",                      "آموزشگاه"),
    ("support_username",   "@support",             "یوزرنیم پشتیبانی (با @)",           "آموزشگاه"),
    ("support_hours",      "۹ صبح تا ۹ شب",       "ساعات پاسخگویی",                    "آموزشگاه"),
    ("about_text",         "آموزشگاه ما با بهترین اساتید...", "متن درباره ما",          "آموزشگاه"),
    # گروه: پرداخت
    ("bank_card",          "6037-XXXX-XXXX-XXXX", "شماره کارت بانکی",                  "پرداخت"),
    ("bank_owner",         "نام صاحب حساب",        "نام صاحب کارت",                     "پرداخت"),
    ("bank_name",          "نام بانک",              "نام بانک",                           "پرداخت"),
    # گروه: کانال
    ("receipt_channel",    "",                     "آیدی کانال رسیدها (مثال: -100xxx)", "کانال"),
    # گروه: سیستم
    ("referral_reward",    "10000",                "پاداش معرف (تومان)",                "سیستم"),
    ("wallet_enabled",     "1",                    "کیف‌پول فعال باشد (1=بله, 0=خیر)", "سیستم"),
    ("referral_enabled",   "1",                    "سیستم معرف فعال باشد",              "سیستم"),
    ("rating_enabled",     "1",                    "امتیازدهی فعال باشد",               "سیستم"),
    ("bot_active",         "1",                    "ربات فعال باشد",                     "سیستم"),
]

# متون پیش‌فرض ربات
DEFAULT_TEXTS = [
    ("welcome",             "سلام {name}! 👋\nبه ربات رسمی {school} خوش آمدید 📚\n\nاز اینجا می‌توانید تمام جزوات آموزشی را خریداری و فوری دریافت کنید.",  "پیام خوش‌آمدگویی"),
    ("choose_category",     "📂 دسته‌بندی مورد نظر را انتخاب کنید:",                         "انتخاب دسته‌بندی"),
    ("choose_product",      "📚 جزوات موجود در این دسته:",                                    "لیست جزوات"),
    ("no_products",         "❌ در این دسته‌بندی جزوه‌ای موجود نیست.",                        "دسته خالی"),
    ("cart_empty",          "🛒 سبد خرید شما خالی است.",                                      "سبد خالی"),
    ("cart_header",         "🛒 سبد خرید شما\n────────────────",                              "عنوان سبد خرید"),
    ("product_added_cart",  "✅ جزوه به سبد خرید اضافه شد!",                                 "افزودن به سبد"),
    ("product_already_cart","⚠️ این جزوه قبلاً در سبد خرید شما است.",                       "تکراری در سبد"),
    ("product_already_bought","⚠️ شما این جزوه را قبلاً خریداری کرده‌اید.\nاز «سفارشات من» دانلود مجدد کنید.", "خرید تکراری"),
    ("coupon_ask",          "آیا کد تخفیف دارید؟",                                           "سوال کد تخفیف"),
    ("coupon_enter",        "🎟️ کد تخفیف خود را وارد کنید:",                                 "ورود کد تخفیف"),
    ("coupon_invalid",      "❌ این کد تخفیف معتبر نیست یا منقضی شده.",                      "کد نامعتبر"),
    ("coupon_valid",        "✅ کد تخفیف اعمال شد!\n🎉 {discount} تومان تخفیف گرفتید.",      "کد معتبر"),
    ("payment_info",        "💳 اطلاعات پرداخت\n────────────────\n🏦 بانک: {bank}\n💳 شماره کارت:\n<code>{card}</code>\n👤 به نام: {owner}\n\n💰 مبلغ: <b>{amount} تومان</b>\n\nپس از واریز، رسید (عکس یا متن) را ارسال کنید:", "اطلاعات کارت به کارت"),
    ("receipt_sent",        "✅ رسید شما ارسال شد.\n\nکد پیگیری: <code>{order_id}</code>\n\nپس از تأیید، فایل‌ها ارسال می‌شوند.", "بعد از ارسال رسید"),
    ("order_approved",      "🎉 پرداخت تأیید شد!\n\nکد سفارش: <code>{order_id}</code>\n\nدر حال آماده‌سازی فایل‌ها...", "تأیید سفارش"),
    ("order_rejected",      "❌ پرداخت شما تأیید نشد.\n\n📝 دلیل: {reason}\n\nلطفاً مجدداً اقدام کنید یا با پشتیبانی تماس بگیرید.", "رد سفارش"),
    ("watermark_done",      "✅ فایل‌های شما آماده‌اند!\n\n⚠️ این فایل‌ها دارای واترمارک اختصاصی شما هستند.\nاشتراک‌گذاری ممنوع است.", "ارسال فایل"),
    ("redownload_ready",    "📥 فایل‌های سفارش #{order_id}:",                                "دانلود مجدد"),
    ("rating_ask",          "⭐ از خرید خود چقدر راضی هستید؟",                               "درخواست امتیاز"),
    ("rating_done",         "🙏 ممنون از نظر شما!",                                           "تأیید امتیاز"),
    ("referral_info",       "🔗 لینک معرف شما:\n{link}\n\nبه ازای هر خرید معرفی‌شده، {reward} تومان به کیف‌پولتان اضافه می‌شود.", "اطلاعات معرف"),
    ("wallet_info",         "👛 موجودی کیف‌پول: <b>{balance} تومان</b>",                     "موجودی کیف‌پول"),
    ("wallet_used",         "✅ {amount} تومان از کیف‌پول کسر شد.",                          "استفاده از کیف‌پول"),
    ("referral_reward_msg", "🎁 {amount} تومان به کیف‌پول شما اضافه شد! (پاداش معرف)",      "پیام پاداش معرف"),
    ("channel_msg",         "📩 رسید جدید\n────────────────\n👤 {name}\n📱 @{username}\n🆔 {user_id}\n💰 {amount} تومان\n🧾 سفارش #{order_id}\n📦 {item_count} جزوه\n⏰ {time}", "متن کانال"),
    ("support_msg",         "📞 پشتیبانی: {username}\n⏰ ساعات: {hours}",                    "پیام پشتیبانی"),
    ("bot_inactive",        "🔴 ربات موقتاً غیرفعال است. به زودی برمی‌گردیم!",              "پیام غیرفعال"),
    # دکمه‌ها
    ("btn_products",        "📂 مشاهده جزوات",    "دکمه مشاهده جزوات"),
    ("btn_cart",            "🛒 سبد خرید",         "دکمه سبد خرید"),
    ("btn_orders",          "📦 سفارشات من",        "دکمه سفارشات"),
    ("btn_profile",         "👤 پروفایل من",        "دکمه پروفایل"),
    ("btn_referral",        "🔗 لینک معرف",         "دکمه لینک معرف"),
    ("btn_wallet",          "👛 کیف‌پول",           "دکمه کیف‌پول"),
    ("btn_support",         "📞 پشتیبانی",          "دکمه پشتیبانی"),
    ("btn_back",            "🔙 بازگشت",            "دکمه بازگشت"),
    ("btn_main",            "🏠 منوی اصلی",         "دکمه منوی اصلی"),
    ("btn_add_cart",        "🛒 افزودن به سبد",     "دکمه افزودن"),
    ("btn_buy_now",         "⚡ خرید سریع",         "دکمه خرید سریع"),
    ("btn_checkout",        "💳 پرداخت نهایی",      "دکمه پرداخت"),
    ("btn_clear_cart",      "🗑️ پاک کردن سبد",     "دکمه پاک کردن"),
    ("btn_use_coupon",      "🎟️ کد تخفیف دارم",    "دکمه کد تخفیف"),
    ("btn_skip_coupon",     "⏭️ ادامه بدون تخفیف", "دکمه رد کد تخفیف"),
    ("btn_use_wallet",      "👛 استفاده از کیف‌پول","دکمه کیف‌پول"),
    ("btn_approve",         "✅ تأیید پرداخت",      "دکمه تأیید کانال"),
    ("btn_reject",          "❌ رد پرداخت",         "دکمه رد کانال"),
    ("btn_redownload",      "📥 دانلود مجدد",       "دکمه دانلود مجدد"),
]


async def init_db():
    os.makedirs("database", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES)
        for key, value, label, group in DEFAULT_SETTINGS:
            await db.execute(
                "INSERT OR IGNORE INTO settings(key,value,label,group_name) VALUES(?,?,?,?)",
                (key, value, label, group)
            )
        for row in DEFAULT_TEXTS:
            await db.execute(
                "INSERT OR IGNORE INTO bot_texts(key,value,description) VALUES(?,?,?)", row
            )
        await db.commit()


# ─── SETTINGS ────────────────────────────────────────────────────────────────

async def get_setting(key: str, default: str = "") -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
    return row[0] if row else default


async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
        await db.commit()


async def get_all_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT key, value, label, group_name FROM settings ORDER BY group_name, key"
        ) as cur:
            return await cur.fetchall()


# ─── BOT TEXTS ───────────────────────────────────────────────────────────────

async def get_text(key: str, **kwargs) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        # اول bot_texts
        async with db.execute("SELECT value FROM bot_texts WHERE key=?", (key,)) as cur:
            row = await cur.fetchone()
        if not row:
            # بعد settings
            async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cur:
                row = await cur.fetchone()
    val = row[0] if row else ""
    if not val:
        return ""
    try:
        return val.format(**kwargs)
    except:
        return val


async def get_all_texts():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT key, value, description FROM bot_texts ORDER BY key"
        ) as cur:
            return await cur.fetchall()


async def set_text(key: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # اگه در bot_texts بود آپدیت کن، وگرنه در settings
        async with db.execute("SELECT key FROM bot_texts WHERE key=?", (key,)) as cur:
            in_texts = await cur.fetchone()
        if in_texts:
            await db.execute("UPDATE bot_texts SET value=? WHERE key=?", (value, key))
        else:
            await db.execute("UPDATE settings SET value=? WHERE key=?", (value, key))
        await db.commit()

async def is_user_banned(tg_id: int) -> bool:
    """چک مسدودیت کاربر — True یعنی مسدوده"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_banned FROM users WHERE tg_id=?", (tg_id,)) as c:
            row = await c.fetchone()
    return row is not None and int(row[0]) == 1