# ToonPay Telegram Test Dashboard

Sandbox/test project only. It does not connect to real ToonPay accounts or real OTP systems.

Railway variables:
BOT_TOKEN
ADMIN_TELEGRAM_ID
APP_URL
DATABASE_PATH=toonpay_test.db

Create two Railway services from this repo:
1. Web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
2. Bot worker: python bot.py

Use the same environment variables on both services.
