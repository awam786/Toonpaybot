import os
import httpx

from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

APP_URL = os.getenv("APP_URL", "").strip().rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "").strip().rstrip("/")


def normalize_url(url: str) -> str:
    if not url:
        return ""

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    return url.rstrip("/")


APP_URL = normalize_url(APP_URL)
BACKEND_URL = normalize_url(BACKEND_URL)


def is_admin(update: Update) -> bool:
    user = update.effective_user

    if not user:
        return False

    return user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Open ToonPay 🚀",
                    web_app=WebAppInfo(url=APP_URL),
                )
            ]
        ]
    )

    await update.message.reply_text(
        "👋 Welcome to ToonPay!\n\n"
        "Tap the button below to open the ToonPay dashboard.",
        reply_markup=keyboard,
    )


async def call_backend(
    method: str,
    endpoint: str,
    *,
    json_data=None,
    params=None,
):
    url = f"{BACKEND_URL}{endpoint}"

    headers = {
        "x-admin-id": str(ADMIN_ID),
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.request(
            method,
            url,
            json=json_data,
            params=params,
            headers=headers,
        )

        response.raise_for_status()

        if response.content:
            return response.json()

        return {}


async def admin_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if not query:
        return

    if not is_admin(update):
        await query.answer(
            "Only the ToonPay admin can use this button.",
            show_alert=True,
        )
        return

    await query.answer()

    data = query.data or ""

    try:
        action, request_id_text = data.split(":", 1)
        request_id = int(request_id_text)
    except (ValueError, AttributeError):
        await query.message.reply_text(
            "❌ Invalid request."
        )
        return

    # ---------------------------------------------------------
    # SET DEMO CODE
    # ---------------------------------------------------------
    if action == "setcode":
        context.user_data["awaiting_demo_code_for"] = request_id

        await query.message.reply_text(
            f"🔐 Request #{request_id}\n\n"
            "Set a synthetic 6-digit demo code for this test login.\n\n"
            "Use:\n"
            f"/setcode {request_id} 123456\n\n"
            "Replace 123456 with the code you want to give the user."
        )

        return

    # ---------------------------------------------------------
    # REJECT REQUEST
    # ---------------------------------------------------------
    if action == "reject":
        try:
            await call_backend(
                "POST",
                f"/internal/admin/reject/{request_id}",
            )

            await query.message.reply_text(
                f"❌ Demo login request #{request_id} rejected."
            )

        except Exception as exc:
            await query.message.reply_text(
                "❌ Could not reject the request.\n\n"
                f"Error: {exc}"
            )

        return


async def set_code(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    if not is_admin(update):
        await update.message.reply_text(
            "❌ Admin only."
        )
        return

    args = context.args

    if len(args) != 2:
        await update.message.reply_text(
            "Usage:\n"
            "/setcode REQUEST_ID 123456"
        )
        return

    try:
        request_id = int(args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ Request ID must be a number."
        )
        return

    code = args[1].strip()

    if len(code) != 6 or not code.isdigit():
        await update.message.reply_text(
            "❌ Demo code must contain exactly 6 digits."
        )
        return

    try:
        await call_backend(
            "POST",
            f"/internal/admin/set-demo-code/{request_id}",
            params={
                "code": code,
            },
        )

        context.user_data.pop(
            "awaiting_demo_code_for",
            None,
        )

        await update.message.reply_text(
            f"✅ Demo code configured for request #{request_id}.\n\n"
            "Give this synthetic code to the user so they can continue "
            "the test login."
        )

    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get(
                "detail",
                "Backend rejected the request.",
            )
        except Exception:
            detail = "Backend rejected the request."

        await update.message.reply_text(
            f"❌ Could not configure demo code.\n\n{detail}"
        )

    except Exception as exc:
        await update.message.reply_text(
            "❌ Could not connect to the ToonPay backend.\n\n"
            f"Error: {exc}"
        )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message:
        return

    await update.message.reply_text(
        "ToonPay Test Bot\n\n"
        "/start - Open the test dashboard\n"
        "/help - Show this help"
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is missing."
        )

    if not APP_URL:
        raise RuntimeError(
            "APP_URL is missing."
        )

    if not BACKEND_URL:
        raise RuntimeError(
            "BACKEND_URL is missing."
        )

    if not ADMIN_ID:
        raise RuntimeError(
            "ADMIN_TELEGRAM_ID is missing."
        )

    print("====================================")
    print("ToonPay Telegram Test Bot")
    print("====================================")
    print(f"ADMIN_ID: {ADMIN_ID}")
    print(f"APP_URL: {APP_URL}")
    print(f"BACKEND_URL: {BACKEND_URL}")
    print("Bot polling started...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CommandHandler("setcode", set_code)
    )

    application.add_handler(
        CallbackQueryHandler(admin_callback)
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()
