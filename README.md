# ToonPay Telegram Test Dashboard

A sandbox Telegram Mini App and Telegram bot for testing a ToonPay-style
login and dashboard flow.

## Important

This project is a DEMO / TEST system.

It does not connect to real ToonPay accounts.

It does not validate real ToonPay passwords.

It does not use real ToonPay OTPs.

The authentication code is a synthetic 6-digit demo code configured by
the administrator.

---

# Project Structure

toonpay_safe/

├── app/
│   ├── __init__.py
│   ├── main.py
│   └── static/
│       ├── index.html
│       ├── app.js
│       ├── style.css
│       └── logo.png
│
├── bot.py
├── database.py
├── requirements.txt
├── railway.json
├── Procfile
├── .env.example
└── README.md

---

# Railway Deployment

Create ONE Railway project.

Create TWO services from the same GitHub repository.

## Service 1 - Web

Example name:

Toonpaybot

Start command:

uvicorn app.main:app --host 0.0.0.0 --port $PORT

Variables:

BOT_TOKEN=your_bot_token

ADMIN_TELEGRAM_ID=8539614189

APP_URL=https://your-web-service.up.railway.app

BACKEND_URL=https://your-web-service.up.railway.app

DATABASE_PATH=toonpay_demo.db

DEMO_CODE_SALT=your_random_secret_value

---

# Service 2 - Telegram Bot

Example name:

zippy-nature

Start command:

python bot.py

Variables:

BOT_TOKEN=your_bot_token

ADMIN_TELEGRAM_ID=8539614189

APP_URL=https://your-web-service.up.railway.app

BACKEND_URL=https://your-web-service.up.railway.app

DEMO_CODE_SALT=your_random_secret_value

DATABASE_PATH=toonpay_demo.db

The bot does not directly access the database. It communicates with
the web service through BACKEND_URL.

---

# APP_URL

APP_URL must point to the public HTTPS URL of the Web service.

Example:

https://toonpaybot-production.up.railway.app

Do not use:

localhost

127.0.0.1

http://127.0.0.1:8000

---

# BACKEND_URL

BACKEND_URL should point to the same public Web service.

Example:

https://toonpaybot-production.up.railway.app

---

# Telegram Bot Flow

User sends:

/start

The bot displays:

Welcome to ToonPay!

Open ToonPay

The user opens the Mini App.

---

# Demo Login Flow

1. User enters an email.

2. Backend creates a login request.

3. Admin receives the request in Telegram.

4. Admin selects:

Set Demo Code

5. Admin sends:

/setcode REQUEST_ID 123456

6. The server stores a hash of the synthetic code.

7. Admin provides the synthetic code to the test user.

8. User enters the code.

9. Server compares the submitted code with the stored hash.

10. If correct, the demo session is approved.

11. The synthetic dashboard opens.

---

# Admin Commands

/setcode REQUEST_ID 123456

Example:

/setcode 12 583921

The code must contain exactly six digits.

---

# Dashboard

The dashboard contains synthetic test information only.

Examples:

Balance

Transactions

Cashback

Points

Plan

Notifications

Referrals

No real financial/account information is retrieved.

---

# Logo

Place the correct ToonPay logo at:

app/static/logo.png

The website uses:

/logo.png

---

# Local Test

Install dependencies:

pip install -r requirements.txt

Run web:

uvicorn app.main:app --reload

Run bot separately:

python bot.py

---

# Security

Never commit:

.env

BOT_TOKEN

real credentials

real OTPs

private keys

API secrets

The demo authentication code should always be treated as synthetic
test data.

---

# Railway Start Commands

Web service:

uvicorn app.main:app --host 0.0.0.0 --port $PORT

Bot service:

python bot.py
