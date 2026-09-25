import os
import asyncio
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
APP_URL = os.getenv("APP_URL", "").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")

# Track admin's pending "which request am I assigning OTP to?"
AWAITING_OTP_FOR: dict[int, int] = {}  # admin_chat_id -> request_id


def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open ToonPay 🚀", web_app=WebAppInfo(url=APP_URL))]]
    )
    await update.message.reply_text(
        "👋 Welcome to ToonPay!\n\n"
        "Tap the button below to open the ToonPay app and get started.",
        reply_markup=keyboard,
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Not authorized.")
        return
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BACKEND_URL}/api/admin/pending")
        data = r.json().get("requests", [])

    if not data:
        await update.message.reply_text("No pending requests.")
        return

    lines = ["<b>Pending Requests</b>\n"]
    buttons = []
    for req in data[:20]:
        lines.append(
            f"#{req['id']} — <code>{req['identifier']}</code> — {req['status']}"
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    f"✏️ Assign #{req['id']}",
                    callback_data=f"assign:{req['id']}",
                )
            ]
        )
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update):
        return

    data = query.data or ""
    action, _, req_id_s = data.partition(":")
    if not req_id_s.isdigit():
        return
    req_id = int(req_id_s)

    if action == "assign":
        AWAITING_OTP_FOR[query.message.chat_id] = req_id
        await query.message.reply_text(
            f"Send me the 6-digit OTP for request <code>#{req_id}</code>:",
            parse_mode="HTML",
        )
        return

    if action == "approve":
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{BACKEND_URL}/api/admin/decision",
                json={"request_id": req_id, "decision": "correct"},
            )
        await query.message.reply_text(f"✅ Approved request #{req_id}. User can log in.")
        return

    if action == "reject":
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{BACKEND_URL}/api/admin/decision",
                json={"request_id": req_id, "decision": "incorrect"},
            )
        await query.message.reply_text(f"❌ Rejected request #{req_id}.")
        return


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    chat_id = update.effective_chat.id
    req_id = AWAITING_OTP_FOR.get(chat_id)
    if not req_id:
        return

    text = (update.message.text or "").strip()
    if len(text) != 6 or not text.isdigit():
        await update.message.reply_text("❌ Send exactly 6 digits.")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            f"{BACKEND_URL}/api/admin/assign",
            json={"request_id": req_id, "otp": text},
        )
    AWAITING_OTP_FOR.pop(chat_id, None)

    if r.status_code == 200:
        await update.message.reply_text(
            f"✅ OTP <code>{text}</code> saved for request #{req_id}.\n"
            f"Now send this code to the user. When they type it, "
            f"I'll notify you to approve.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Failed to save OTP.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
