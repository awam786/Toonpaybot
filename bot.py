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

db.init_db()

def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID

def _user_meta(update: Update):
    u = update.effective_user
    if not u: return None, "", ""
    return u.id, u.username or "", u.first_name or ""

async def _log(tg_id, username, first_name, action, detail=""):
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(f"{BACKEND_URL}/api/log-activity", json={"telegram_id": tg_id, "username": username, "first_name": first_name, "action": action, "detail": detail})
    except Exception as e:
        print("log failed:", e)

# ==========================================================
# TRACK GROUPS & CHANNELS
# ==========================================================
async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        db.track_chat(chat.id, chat.title or "Unknown", chat.type)

# ==========================================================
# USER COMMANDS
# ==========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id, username, first_name = _user_meta(update)
    await _log(tg_id, username, first_name, "/start", "opened bot")

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Open ToonPay 🚀", web_app=WebAppInfo(url=APP_URL))]])
    await update.message.reply_text("👋 Welcome to ToonPay!\n\nTap the button below to open the ToonPay app and get started.", reply_markup=kb)

# ==========================================================
# ADMIN COMMANDS
# ==========================================================
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
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
        buttons.append([InlineKeyboardButton(f"✏️ Assign #{req['id']}", callback_data=f"assign:{req['id']}")])
    await update.message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    BROADCAST_STATE[update.effective_user.id] = {"step": "waiting_for_message"}
    await update.message.reply_text("📢 <b>Broadcast Mode</b>\n\nPlease send the message you want to broadcast.\n\nSend /cancel to abort.", parse_mode="HTML")

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    BROADCAST_STATE.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Broadcast cancelled.")

async def skip_button_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    admin_id = update.effective_user.id
    state = BROADCAST_STATE.get(admin_id)
    
    if state and state["step"] == "waiting_for_button":
        state["step"] = "waiting_for_target"
        state["reply_markup"] = None
        await show_target_menu(update.message)
    else:
        await update.message.reply_text("No active broadcast to skip button for.")

async def show_target_menu(message):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 All Users", callback_data="bcast:users")],
        [InlineKeyboardButton("🎯 Specific Users", callback_data="bcast:specific")],
        [InlineKeyboardButton("👥 All Groups", callback_data="bcast:groups")],
        [InlineKeyboardButton("🎯 Specific Groups", callback_data="bcast:specific_groups")],
        [InlineKeyboardButton("📢 All Channels", callback_data="bcast:channels")],
    ])
    await message.reply_text("✅ Setup complete.\n\n<b>Where do you want to send this?</b>", reply_markup=kb, parse_mode="HTML")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Please reply to the message you want to delete with /delete")
        return
        
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=update.message.reply_to_message.message_id
        )
        await update.message.delete()
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to delete message.\n<i>Error: {e}</i>", parse_mode="HTML")

# ==========================================================
# CALLBACKS (BUTTONS)
# ==========================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update): return

    data = query.data or ""
    admin_id = update.effective_user.id

    if data.startswith("bcast:"):
        state = BROADCAST_STATE.get(admin_id)
        if not state or "msg" not in state: return

        target = data.split(":")[1]
        reply_markup = state.get("reply_markup")
        
        if target == "users":
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{BACKEND_URL}/api/admin/all-users")
                user_ids = r.json().get("users", [])
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(user_ids)}</b> users...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], user_ids, "users", context, reply_markup)
            BROADCAST_STATE.pop(admin_id, None)

        elif target == "groups":
            chats = db.get_tracked_chats(ChatType.GROUP) + db.get_tracked_chats(ChatType.SUPERGROUP)
            chat_ids = [c["chat_id"] for c in chats]
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(chat_ids)}</b> groups...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], chat_ids, "groups", context, reply_markup)
            BROADCAST_STATE.pop(admin_id, None)

        elif target == "specific_groups":
            state["step"] = "waiting_for_group_ids"
            await query.message.edit_text(
                "🎯 <b>Specific Groups</b>\n\n"
                "Send the Group IDs separated by commas (e.g., <code>-1001234567890, -1009876543210</code>).\n\n"
                "<i>(Note: Group IDs always start with -100)</i>",
                parse_mode="HTML"
            )

        elif target == "channels":
            chats = db.get_tracked_chats(ChatType.CHANNEL)
            chat_ids = [c["chat_id"] for c in chats]
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(chat_ids)}</b> channels...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], chat_ids, "channels", context, reply_markup)
            BROADCAST_STATE.pop(admin_id, None)

        elif target == "specific":
            state["step"] = "waiting_for_ids"
            await query.message.edit_text("🎯 <b>Specific Users</b>\n\nSend the Telegram IDs separated by commas (e.g., <code>123456789, 987654321</code>):", parse_mode="HTML")
        return

    if data == "refresh_users":
        await send_users_list(query.message.chat_id, context)
        return

    if data.startswith("user:"):
        tg_id = int(data.split(":", 1)[1])
        await show_user_detail(query.message.chat_id, tg_id, context)
        return

    action, _, req_id_s = data.partition(":")
    if not req_id_s.isdigit(): return
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
# TEXT HANDLER
# ==========================================================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return

    admin_id = update.effective_user.id
    chat_id = update.effective_chat.id
    state = BROADCAST_STATE.get(admin_id)
    
    if state:
        if state["step"] == "waiting_for_message":
            state["msg"] = update.message
            state["step"] = "waiting_for_button"
            await update.message.reply_text("✅ Message received.\n\nDo you want to add an inline button?\nSend: <code>Button Text | https://yourlink.com</code>\n\n<i>(To force open the app, use: app:https://yourlink.com)</i>\n\nOr send /skip to continue without a button.", parse_mode="HTML")
            return

        if state["step"] == "waiting_for_button":
            text = update.message.text or ""
            if "|" not in text:
                await update.message.reply_text("❌ Invalid format. Send <code>Button Text | https://yourlink.com</code> or /skip.", parse_mode="HTML")
                return
            
            btn_text, url = [x.strip() for x in text.split("|", 1)]
            clean_url = url.replace("app:", "").rstrip('/')
            clean_app = APP_URL.rstrip('/')
            
            if clean_url == clean_app or url.startswith("app:"):
                state["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, web_app=WebAppInfo(url=clean_url))]])
            else:
                state["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, url=url)]])
                
            state["step"] = "waiting_for_target"
            await show_target_menu(update.message)
            return

        if state["step"] == "waiting_for_ids":
            text = update.message.text.replace(" ", "")
            try:
                ids = [int(i.strip()) for i in text.split(",") if i.strip()]
                if not ids: raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Invalid format. Send User IDs separated by commas.")
                return
            await update.message.reply_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> specific users...", parse_mode="HTML")
            await execute_broadcast(update.message, state["msg"], ids, "specific users", context, state.get("reply_markup"))
            BROADCAST_STATE.pop(admin_id, None)
            return

        if state["step"] == "waiting_for_group_ids":
            text = update.message.text.replace(" ", "")
            try:
                ids = [int(i.strip()) for i in text.split(",") if i.strip()]
                if not ids: raise ValueError
            except ValueError:
                await update.message.reply_text("❌ Invalid format. Send Group IDs separated by commas.")
                return
            await update.message.reply_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> specific groups...", parse_mode="HTML")
            await execute_broadcast(update.message, state["msg"], ids, "specific groups", context, state.get("reply_markup"))
            BROADCAST_STATE.pop(admin_id, None)
            return

    req_id = AWAITING_OTP_FOR.get(chat_id)
    if req_id:
        text = (update.message.text or "").strip()
        if len(text) != 6 or not text.isdigit():
            await update.message.reply_text("❌ Send exactly 6 digits.")
            return

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{BACKEND_URL}/api/admin/assign", json={"request_id": req_id, "otp": text})
        AWAITING_OTP_FOR.pop(chat_id, None)
        if r.status_code == 200:
            await update.message.reply_text(f"✅ OTP <code>{text}</code> saved for request #{req_id}.", parse_mode="HTML")
        else:
            await update.message.reply_text("⚠️ Failed to save OTP.")

# ==========================================================
# BROADCAST EXECUTION ENGINE (UPDATED FOR TIMEOUTS)
# ==========================================================
async def execute_broadcast(progress_msg, broadcast_msg, chat_ids, target_name, context, reply_markup=None):
    success = 0
    failed = 0
    
    status_msg = await progress_msg.reply_text(f"⏳ Progress: 0/{len(chat_ids)}")

    for index, chat_id in enumerate(chat_ids, 1):
        try:
            # Copy the message
            await broadcast_msg.copy(chat_id=chat_id, reply_markup=reply_markup)
            success += 1
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")
            failed += 1
        
        # Update progress every 10 sends safely inside a try/except
        if index % 10 == 0 or index == len(chat_ids):
            try:
                await status_msg.edit_text(f"⏳ Progress: {index}/{len(chat_ids)}\n✅ Success: {success} | ❌ Failed: {failed}")
            except Exception:
                pass # If updating the progress bar times out, we ignore it and keep broadcasting
                
        # INCREASED SLEEP DELAY: 0.1 seconds (10 messages per second)
        # This is much safer and prevents Telegram timeouts
        await asyncio.sleep(0.1)

    try:
        await status_msg.edit_text(f"🏁 <b>Broadcast Finished!</b>\n\n🎯 Target: {target_name}\n✅ Success: {success}\n❌ Failed: {failed}", parse_mode="HTML")
    except Exception:
        pass

# ==========================================================
# STATUS COMMAND
# ==========================================================
async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
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
    try: return datetime.datetime.fromtimestamp(int(ts)).strftime("%b %d, %H:%M")
    except: return "?"

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
        f"Last seen:  {_fmt_ts(summary['last_seen'])}\n\n<b>📋 History:</b>\n───────────────────────"
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
# MAIN (UPDATED TIMEOUT SETTINGS)
# ==========================================================
def main():
    # Increased timeouts to 30 seconds to prevent TimedOut errors on Railway
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("cancel", cancel_broadcast))
    app.add_handler(CommandHandler("skip", skip_button_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, track_chats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, text_handler))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
