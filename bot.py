import os
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

AWAITING_OTP_FOR: dict[int, int] = {}


def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID


def _user_meta(update: Update):
    u = update.effective_user
    if not u:
        return None, "", ""
    return u.id, u.username or "", u.first_name or ""


async def _log(tg_id, username, first_name, action, detail=""):
    """Send an activity log to the backend with the correct action name."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(
                f"{BACKEND_URL}/api/log-activity",
                json={
                    "telegram_id": tg_id,
                    "username": username,
                    "first_name": first_name,
                    "action": action,
                    "detail": detail,
                },
            )
    except Exception as e:
        print("log failed:", e)


# ---------- /start ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id, username, first_name = _user_meta(update)
    await _log(tg_id, username, first_name, "/start", "opened bot")

    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Open ToonPay 🚀", web_app=WebAppInfo(url=APP_URL))]]
    )
    await update.message.reply_text(
        "👋 Welcome to ToonPay!\n\n"
        "Tap the button below to open the ToonPay app and get started.",
        reply_markup=kb,
    )


# ---------- /admin ----------

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Not authorized.")
        return

    tg_id, username, first_name = _user_meta(update)
    await _log(tg_id, username, first_name, "/admin", "opened admin panel")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BACKEND_URL}/api/admin/pending")
        data = r.json().get("requests", [])

    if not data:
        await update.message.reply_text("No pending requests.")
        return

    lines = ["<b>Pending Requests</b>\n"]
    buttons = []
    for req in data[:20]:
        lines.append(f"#{req['id']} — <code>{req['identifier']}</code> — {req['status']}")
        buttons.append([
            InlineKeyboardButton(f"✏️ Assign #{req['id']}", callback_data=f"assign:{req['id']}")
        ])
    await update.message.reply_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
    )


# ---------- /status ----------

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Not authorized.")
        return
    await send_users_list(update.effective_chat.id, context)


async def send_users_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BACKEND_URL}/api/admin/users")
        users = r.json().get("users", [])

    if not users:
        await context.bot.send_message(chat_id=chat_id, text="No users yet.")
        return

    lines = ["<b>👥 Users (recent activity)</b>\n"]
    buttons = []
    for u in users[:25]:
        name = u.get("first_name") or "User"
        uname = f"@{u['username']}" if u.get("username") else ""
        lines.append(
            f"• <b>{name}</b> {uname} — <code>{u['telegram_id']}</code>\n"
            f"   actions: {u['total_actions']} | last: {_fmt_ts(u['last_seen'])}"
        )
        buttons.append([
            InlineKeyboardButton(
                f"📋 {name} ({u['telegram_id']})",
                callback_data=f"user:{u['telegram_id']}",
            )
        ])
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh_users")])

    await context.bot.send_message(
        chat_id=chat_id,
        text="\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


def _fmt_ts(ts):
    import datetime
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%b %d, %H:%M")
    except Exception:
        return "?"


async def show_user_detail(chat_id, telegram_id, context: ContextTypes.DEFAULT_TYPE):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{BACKEND_URL}/api/admin/user/{telegram_id}")
        data = r.json()

    summary = data.get("summary") or {}
    activity = data.get("activity") or []

    if not summary:
        await context.bot.send_message(chat_id=chat_id, text="No data for this user.")
        return

    header = (
        f"👤 <b>{summary.get('first_name') or 'User'}</b> "
        f"{('@' + summary['username']) if summary.get('username') else ''}\n"
        f"Telegram ID: <code>{telegram_id}</code>\n"
        f"First seen: {_fmt_ts(summary['first_seen'])}\n"
        f"Last seen:  {_fmt_ts(summary['last_seen'])}\n"
        f"Total actions: {summary['total_actions']}\n\n"
        f"<b>📋 Movement history (latest 30):</b>\n"
        f"───────────────────────"
    )
    lines = [header]
    for a in activity:
        ts = _fmt_ts(a["created_at"])
        detail = a.get("detail") or ""
        lines.append(f"• {ts} — {a['action']}" + (f" — {detail}" if detail else ""))

    text = "\n".join(lines)
    chunks = [text[i:i + 3800] for i in range(0, len(text), 3800)]
    for chunk in chunks:
        await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")


# ---------- Inline button handler ----------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update):
        return

    data = query.data or ""

    if data == "refresh_users":
        await send_users_list(query.message.chat_id, context)
        return

    if data.startswith("user:"):
        tg_id = int(data.split(":", 1)[1])
        await show_user_detail(query.message.chat_id, tg_id, context)
        return

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


# ---------- Text handler (admin types OTP) ----------

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
            f"Send it to the user. When they submit, I'll notify you.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ Failed to save OTP.")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
