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
    WebAppInfo
)


load_dotenv()


BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    ""
)

ADMIN_ID = int(
    os.getenv(
        "ADMIN_TELEGRAM_ID",
        "0"
    )
)

APP_URL = os.getenv(
    "APP_URL",
    ""
).strip().rstrip("/")

BACKEND_URL = os.getenv(
    "BACKEND_URL",
    ""
).strip().rstrip("/")


bot = Bot(BOT_TOKEN)

dp = Dispatcher()


@dp.message(CommandStart())
async def start(m: Message):

    if not APP_URL.startswith("https://"):

        await m.answer(
            "Welcome to ToonPay Demo.\n\n"
            "Configure APP_URL with your HTTPS "
            "Mini App URL first."
        )

        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Open ToonPay 🚀",
                    web_app=WebAppInfo(
                        url=APP_URL
                    )
                )
            ]
        ]
    )

    await m.answer(
        "👋 Welcome to ToonPay Demo\n\n"
        "Tap below to open the demo dashboard.",
        reply_markup=kb
    )


async def admin_action(
    c: CallbackQuery,
    ok: bool
):

    if c.from_user.id != ADMIN_ID:

        await c.answer(
            "Admin only.",
            show_alert=True
        )

        return

    rid = int(
        c.data.split(":")[1]
    )

    endpoint = (
        "approve"
        if ok
        else
        "reject"
    )

    if not BACKEND_URL.startswith("https://"):

        await c.answer(
            "Backend URL is not configured.",
            show_alert=True
        )

        return

    try:

        async with httpx.AsyncClient(
            timeout=15
        ) as client:

            r = await client.post(
                f"{BACKEND_URL}"
                f"/internal/admin/"
                f"{endpoint}/{rid}",

                headers={
                    "X-Admin-ID":
                    str(ADMIN_ID)
                }
            )

        if r.status_code != 200:

            await c.answer(
                "Backend error.",
                show_alert=True
            )

            return

        await c.answer(
            "Demo approved ✅"
            if ok
            else
            "Demo rejected ❌"
        )

        suffix = (
            "\n\n━━━━━━━━━━━━━━\n"
            "✅ DEMO APPROVED\n"
            "The simulated dashboard can now open."
            if ok
            else
            "\n\n━━━━━━━━━━━━━━\n"
            "❌ DEMO REJECTED\n"
            "User must try again."
        )

        await c.message.edit_text(
            c.message.text + suffix
        )

    except Exception:

        await c.answer(
            "Backend is not reachable.",
            show_alert=True
        )


@dp.callback_query(
    F.data.startswith("otp_ok:")
)
async def ok(c: CallbackQuery):

    await admin_action(
        c,
        True
    )


@dp.callback_query(
    F.data.startswith("otp_bad:")
)
async def bad(c: CallbackQuery):

    await admin_action(
        c,
        False
    )


async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    print(
        "ToonPay Demo Telegram bot running..."
    )

    print(
        "APP_URL:",
        APP_URL
    )

    print(
        "BACKEND_URL:",
        BACKEND_URL
    )

    print(
        "ADMIN_ID:",
        ADMIN_ID
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(main())
