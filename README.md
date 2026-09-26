<div align="center">

# 📚 Telegram Booklet Shop Bot

**A Telegram bot for selling educational booklets and study files.** It covers student registration, receipt-based payments, **automatic delivery of files watermarked for each buyer**, coupons, a wallet, referrals and a full admin panel inside the bot.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21%2B-2CA5E0?logo=telegram&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white)

</div>

---

## ✨ Features

### 🎓 For students
- **Step-by-step registration:** full name, national ID (validated), mobile number (with a contact-share button), province/city picker and grade. Persian digits are normalized automatically.
- **Mandatory channel membership** (public or private channels) with a "check again" button.
- A **catalog by grade → subject → booklet**, showing price, format, sales count and average rating.
- Cart, "buy now", and **discount coupons** (percentage or fixed, with total and per-user limits).
- **Wallet** balance can be used at checkout.
- **Card-to-card payment:** the student uploads a photo of the receipt, which is posted to a private admin channel with Approve/Reject buttons.
- **Automatic delivery on approval:** every file is **watermarked with the buyer's name, phone and national ID** and sent with `protect_content` (no forwarding or saving).
- Re-download of purchased files at any time, order history, and a **post-purchase rating**.
- **Referral link:** the referrer's wallet is credited when the invited user's first order is approved.
- Profile editing, support and about pages.

### 🔏 Per-buyer watermark
| File type | What happens |
|---|---|
| PDF | A faint diagonal stamp in the middle of every page (name, mobile, national ID) plus an info line at the bottom |
| JPG / PNG / WEBP | A repeating diagonal stamp across the whole image |
| Word, PowerPoint, Excel, ZIP... | Sent unchanged, but still protected against forwarding |

Persian text is shaped correctly with the bundled **Vazirmatn** font (SIL OFL, see `assets/fonts/OFL.txt`). If watermarking ever fails, the original file is still delivered, so a purchase never gets stuck.

### 🛠️ Admin panel (`/admin` or the "⚙️ Admin panel" button)
- Dashboard with users, active booklets, pending payments, and today's and total sales.
- **Booklets:** upload the file, then enter title, description (`/skip`), price, grade and subject. Every field can be edited or replaced later, and booklets can be enabled, disabled or deleted.
- **Grades and subjects** management.
- **Orders**, **users** (ban/unban, wallet top-up), **wallets**, **coupons**, **sales statistics** and best-sellers.
- **Broadcast** of any message type (text, photo, video...) to all users (`/cancel` to abort).
- **Mandatory channels:** add or remove channels and turn the requirement on or off.
- **Every bot text and setting is editable from inside the bot**, including school name, bank card, receipt channel, referral reward, and toggles for wallet, referral, rating and the bot itself. Only the token and admin IDs live in `.env`.

## 🧰 Tech Stack
Python · python-telegram-bot (async) · aiosqlite · pypdf + reportlab (PDF watermark) · Pillow (image watermark) · arabic-reshaper + python-bidi · jdatetime

## 🚀 Getting Started
```bash
git clone https://github.com/mohagheghm511/telegram-jozveh-shop-bot.git
cd telegram-jozveh-shop-bot
pip install -r requirements.txt
cp .env.example .env      # set BOT_TOKEN and ADMIN_IDS
python bot.py
```

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Bot token from @BotFather |
| `ADMIN_IDS` | Comma-separated numeric Telegram IDs of the admins |

The database is created **empty on first run**. Then open the bot, send `/admin`, and in **Settings** set your school name, bank card details and the **receipt channel ID**. Add the bot as an admin of that channel, then create grades, subjects and booklets.

**Commands:** `/start` · `/menu` · `/admin` · `/cancel` (abort any form) · `/skip` (skip the booklet description)

## 📁 Project Structure
```
bot.py            # entry point: callback & message routing, guards, error handling
config/           # env loading, conversation states, is_admin()
database/db.py    # schema, default settings & texts, settings/text helpers
handlers/
  ├── registration.py  # channel check, sign-up, province/city, profile editing
  ├── user.py          # catalog, cart, checkout, receipts, approval, delivery, wallet, referral
  └── admin.py         # admin panel
utils/
  ├── helpers.py       # formatting, referral codes, Jalali time, file extension
  └── watermark.py     # per-buyer PDF / image watermark
assets/fonts/     # Vazirmatn font (OFL) for Persian watermarks
```

---
<div align="center">Built by <a href="https://github.com/mohagheghm511">@mohagheghm511</a></div>
