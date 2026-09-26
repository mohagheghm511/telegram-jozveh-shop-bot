<div align="center">

# 📚 Telegram Booklet Shop Bot

**A Telegram bot for selling educational booklets and study files**, with student registration, receipt-based payments, automatic file delivery, coupons, a wallet and a full admin panel inside the bot.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21%2B-2CA5E0?logo=telegram&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?logo=sqlite&logoColor=white)

</div>

---

## ✨ Features

### 🎓 For students
- **Step-by-step registration:** full name, national ID (validated), mobile number (contact share), province and grade. Persian digits are normalized automatically.
- A **catalog by category and grade**, with product details and prices.
- **Payment by card-to-card receipt:** the student uploads a photo of the receipt and the admin approves or rejects it with a reason. **The file is delivered automatically on approval.**
- **Wallet** balance and **discount coupons** (percentage or fixed, with total and per-user limits).
- **Referral link** with rewards, plus **post-purchase rating**.
- **Mandatory channel membership** (public or private channels).
- Support contact.

### 🛠️ Admin panel
- Products: upload file, title, description, price, category and grade, all editable.
- Category and grade management.
- Receipt review queue (approve or reject with a reason).
- Coupon builder, wallet top-ups, **broadcasts**.
- **Edit every bot text and setting** from inside the bot. Only the token and admin IDs live in `.env`.
- Channel-join configuration.

## 🧰 Tech Stack
Python · python-telegram-bot · aiosqlite (async SQLite)

## 🚀 Getting Started
```bash
pip install -r requirements.txt
cp .env.example .env      # BOT_TOKEN and ADMIN_IDS
python bot.py
```
The database is created **empty on first run**.

## 📁 Project Structure
```
config/      # env loading, conversation states
database/    # async SQLite layer and default settings/texts
handlers/    # registration, user shop flows, admin panel
```

---
<div align="center">Built by <a href="https://github.com/mohagheghm511">@mohagheghm511</a></div>
