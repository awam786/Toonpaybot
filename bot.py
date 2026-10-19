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
from telegram.constants import ChatType
import database as db

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
APP_URL = os.getenv("APP_URL", "").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")

AWAITING_OTP_FOR: dict[int, int] = {}
BROADCAST_STATE = {}

# Initialize DB just in case the Bot starts before the Web server (to avoid tracking errors)
db.init_db()

def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID


def _user_meta(update: Update):
    u = update.effective_user
    if not u:
        return None, "", ""
    return u.id, u.username or "", u.first_name or ""


async def _log(tg_id, username, first_name, action, detail=""):
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


# ==========================================================
# TRACK GROUPS & CHANNELS
# ==========================================================

async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        # Using local DB just for tracking group IDs safely
        db.track_chat(chat.id, chat.title or "Unknown", chat.type)
        print(f"Tracked {chat.type}: {chat.title}")


# ==========================================================
# USER COMMANDS
# ==========================================================

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


# ==========================================================
# ADMIN COMMANDS
# ==========================================================

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ Not authorized.")
        return
    await _log(*_user_meta(update), "/admin", "opened admin panel")

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


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    BROADCAST_STATE[update.effective_user.id] = {"step": "waiting_for_message"}
    await update.message.reply_text(
        "📢 <b>Broadcast Mode</b>\n\n"
        "Please send the message you want to broadcast (Text, Photo, Video, etc).\n\n"
        "Send /cancel to abort.",
        parse_mode="HTML"
    )


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    BROADCAST_STATE.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Broadcast cancelled.")


# ==========================================================
# CALLBACKS (BUTTONS)
# ==========================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update):
        return

    data = query.data or ""
    admin_id = update.effective_user.id

    # --- BROADCAST FLOW ---
    if data.startswith("bcast:"):
        state = BROADCAST_STATE.get(admin_id)
        if not state or "msg" not in state:
            await query.message.edit_text("Error: Message lost. Start over with /broadcast")
            return

        target = data.split(":")[1]
        
        if target == "users":
            # Fetch users from the Web API, NOT the local DB!
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{BACKEND_URL}/api/admin/all-users")
                user_ids = r.json().get("users", [])
            
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(user_ids)}</b> users...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], user_ids, "users", context)
            BROADCAST_STATE.pop(admin_id, None)

        elif target == "groups":
            chats = db.get_tracked_chats(ChatType.GROUP)
            chats += db.get_tracked_chats(ChatType.SUPERGROUP)
            chat_ids = [c["chat_id"] for c in chats]
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(chat_ids)}</b> groups...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], chat_ids, "groups", context)
            BROADCAST_STATE.pop(admin_id, None)

        elif target == "channels":
            chats = db.get_tracked_chats(ChatType.CHANNEL)
            chat_ids = [c["chat_id"] for c in chats]
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(chat_ids)}</b> channels...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], chat_ids, "channels", context)
            BROADCAST_STATE.pop(admin_id, None)

        elif target == "specific":
            state["step"] = "waiting_for_ids"
            await query.message.edit_text(
                "🎯 <b>Specific Users</b>\n\n"
                "Send the Telegram IDs separated by commas (e.g., <code>123456789, 987654321</code>).",
                parse_mode="HTML"
            )
        return

    # --- OTP & STATUS FLOW ---
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
        await query.message.reply_text(f"Send me the 6-digit OTP for request <code>#{req_id}</code>:", parse_mode="HTML")
        return

    if action == "approve":
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{BACKEND_URL}/api/admin/decision", json={"request_id": req_id, "decision": "correct"})
        await query.message.reply_text(f"✅ Approved request #{req_id}. User can log in.")
        return

    if action == "reject":
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{BACKEND_URL}/api/admin/decision", json={"request_id": req_id, "decision": "incorrect"})
        await query.message.reply_text(f"❌ Rejected request #{req_id}.")
        return


# ==========================================================
# TEXT HANDLER (OTP ASSIGN & BROADCAST PREP)
# ==========================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    admin_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    state = BROADCAST_STATE.get(admin_id)
    if state:
        if state["step"] == "waiting_for_message":
            state["msg"] = update.message
            state["step"] = "waiting_for_target"
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 All Users", callback_data="bcast:users")],
                [InlineKeyboardButton("🎯 Specific Users", callback_data="bcast:specific")],
                [InlineKeyboardButton("👥 All Groups", callback_data="bcast:groups")],
                [InlineKeyboardButton("📢 All Channels", callback_data="bcast:channels")],
            ])
            await update.message.reply_text(
                "✅ Message received.\n\n<b>Where do you want to send this?</b>",
                reply_markup=kb,
                parse_mode="HTML"
            )
            return

        if state["step"] == "waiting_for_ids":
            text = update.message.text.replace(" ", "")
            try:
                ids = [int(i.strip()) for i in text.split(",") if i.strip()]
                if not ids:
                    raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Invalid format. Send IDs separated by commas.")
                return

            await update.message.reply_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> specific users...", parse_mode="HTML")
            await execute_broadcast(update.message, state["msg"], ids, "users", context)
            BROADCAST_STATE.pop(admin_id, None)
            return

    req_id = AWAITING_OTP_FOR.get(chat_id)
    if req_id:
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


# ==========================================================
# BROADCAST EXECUTION ENGINE (Fixed Signature)
# ==========================================================

async def execute_broadcast(progress_msg, broadcast_msg, chat_ids, target_name, context):
    success = 0
    failed = 0
    
    # Send initial status
    status_msg = await progress_msg.reply_text(f"⏳ Progress: 0/{len(chat_ids)}")

    for index, chat_id in enumerate(chat_ids, 1):
        try:
            # Copy the message the admin sent
            await broadcast_msg.copy(chat_id=chat_id)
            success += 1
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")
            failed += 1
        
        # Update progress every 10 sends to avoid Telegram edit limits
        if index % 10 == 0 or index == len(chat_ids):
            try:
                await status_msg.edit_text(
                    f"⏳ Progress: {index}/{len(chat_ids)}\n✅ Success: {success} | ❌ Failed: {failed}"
                )
            except:
                pass
        
        # Anti-spam delay (crucial)
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"🏁 <b>Broadcast Finished!</b>\n\n"
        f"🎯 Target: {target_name}\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}",
        parse_mode="HTML"
    )


# ==========================================================
# STATUS COMMAND
# ==========================================================

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
        lines.append(f"• <b>{name}</b> {uname} — <code>{u['telegram_id']}</code>")
        buttons.append([InlineKeyboardButton(f"📋 {name} ({u['telegram_id']})", callback_data=f"user:{u['telegram_id']}")])
    
    buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh_users")])
    await context.bot.send_message(chat_id=chat_id, text="\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


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
        f"👤 <b>{summary.get('first_name') or 'User'}</b>\n"
        f"ID: <code>{telegram_id}</code> | Total actions: {summary['total_actions']}\n"
        f"First seen: {_fmt_ts(summary['first_seen'])}\n"
        f"Last seen:  {_fmt_ts(summary['last_seen'])}\n\n"
        f"<b>📋 History:</b>\n───────────────────────"
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


# ==========================================================
# MAIN
# ==========================================================

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))
    
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, track_chats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, text_handler))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
