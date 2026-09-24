import asyncio
import os
import httpx

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

APP_URL = os.getenv("APP_URL", "").strip()

# Railway web-service URL.
# Locally it can fall back to localhost.
BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "http://127.0.0.1:8000"
).strip().rstrip("/")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    if not APP_URL.startswith("https://"):
        await message.answer(
            "👋 Welcome to ToonPay!\n\n"
            "The test Mini App is not configured yet.\n"
            "Please configure APP_URL with your HTTPS Railway URL."
        )
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Open ToonPay 🚀",
                    web_app=WebAppInfo(url=APP_URL),
                )
            ]
        ]
    )

    await message.answer(
        "👋 Welcome to ToonPay!\n\n"
        "Tap the button below to open the ToonPay test dashboard.",
        reply_markup=keyboard,
    )


async def admin_action(callback: CallbackQuery, approved: bool):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer(
            "Admin only.",
            show_alert=True,
        )
        return

    try:
        request_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(
            "Invalid request.",
            show_alert=True,
        )
        return

    endpoint = "approve" if approved else "reject"

    url = (
        f"{BACKEND_URL}"
        f"/internal/admin/{endpoint}/{request_id}"
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                url,
                headers={
                    "X-Admin-ID": str(ADMIN_ID)
                },
            )

        if response.status_code != 200:
            await callback.answer(
                f"Backend error: {response.status_code}",
                show_alert=True,
            )
            return

        if approved:
            await callback.answer("OTP approved ✅")

            suffix = (
                "\n\n━━━━━━━━━━━━━━\n"
                "✅ OTP APPROVED\n"
                "User can now enter ToonPay."
            )
        else:
            await callback.answer("OTP rejected ❌")

            suffix = (
                "\n\n━━━━━━━━━━━━━━\n"
                "❌ OTP REJECTED\n"
                "User must try again."
            )

        current_text = callback.message.text or ""

        # Prevent duplicate status text if the same message is edited again.
        if "OTP APPROVED" not in current_text and "OTP REJECTED" not in current_text:
            await callback.message.edit_text(
                current_text + suffix
            )

    except Exception as error:
        print(
            f"Backend request failed: {type(error).__name__}: {error}"
        )

        await callback.answer(
            "Backend is not reachable.",
            show_alert=True,
        )


@dp.callback_query(F.data.startswith("otp_ok:"))
async def otp_ok(callback: CallbackQuery):
    await admin_action(callback, True)


@dp.callback_query(F.data.startswith("otp_bad:"))
async def otp_bad(callback: CallbackQuery):
    await admin_action(callback, False)


async def main():
    print("====================================")
    print("ToonPay Telegram Test Bot")
    print("====================================")
    print(f"APP_URL: {APP_URL}")
    print(f"BACKEND_URL: {BACKEND_URL}")
    print(f"ADMIN_ID: {ADMIN_ID}")
    print("Bot polling started...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
