import os
import sys
import asyncio
import httpx
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, Bot
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from telegram.constants import ChatType
from telegram.error import Forbidden, BadRequest
import database as db

ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
APP_URL = os.getenv("APP_URL", "").rstrip("/")
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")

AWAITING_OTP_FOR = {}
BROADCAST_STATE = {}

def is_admin(update: Update) -> bool:
    return update.effective_user and update.effective_user.id == ADMIN_ID

def _user_meta(update: Update):
    u = update.effective_user
    if not u: return None, "", ""
    return u.id, u.username or "", u.first_name or ""

async def _log(tg_id, username, first_name, action, detail="", bot_source="main"):
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(f"{BACKEND_URL}/api/log-activity", json={"telegram_id": tg_id, "username": username, "first_name": first_name, "action": action, "detail": detail, "bot_source": bot_source})
    except: pass

def _fmt_ts(ts):
    try: return datetime.datetime.fromtimestamp(int(ts)).strftime("%b %d, %H:%M")
    except: return "?"

# ==========================================================
# TRACK CHATS
# ==========================================================
async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        db.track_chat(chat.id, chat.title or "Unknown", chat.type, context.bot.username)

# ==========================================================
# USER COMMANDS
# ==========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id, username, first_name = _user_meta(update)
    await _log(tg_id, username, first_name, "/start", "opened bot", context.bot.username)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Open ToonPay 🚀", web_app=WebAppInfo(url=APP_URL))]])
    await update.message.reply_text("👋 Welcome to ToonPay!\n\nTap the button below to open the ToonPay app and get started.", reply_markup=kb)

# ==========================================================
# ADMIN COMMANDS
# ==========================================================
async def clone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    try: new_token = context.args[0]
    except IndexError:
        await update.message.reply_text("⚠️ Usage: `/clone <bot_token>`", parse_mode="HTML")
        return

    if ":" not in new_token:
        await update.message.reply_text("❌ Invalid token format.")
        return

    msg = await update.message.reply_text("⏳ Validating new clone token...")
    try:
        test_bot = Bot(token=new_token)
        bot_info = await test_bot.get_me()
        await test_bot.close()
    except Exception as e:
        await msg.edit_text(f"❌ Invalid token!\nError: {e}")
        return

    db.add_clone(bot_info.id, bot_info.username, new_token)
    await msg.edit_text(f"✅ Clone @{bot_info.username} added successfully!\n\n🔄 Restarting system to launch new clone...", parse_mode="HTML")
    await asyncio.sleep(2)
    os.execv(sys.executable, ['python'] + sys.argv)

async def migrate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    try: new_token = context.args[0]
    except IndexError:
        await update.message.reply_text("⚠️ Usage: `/migrate <new_bot_token>`")
        return

    msg = await update.message.reply_text("⏳ Validating new main token...")
    try:
        test_bot = Bot(token=new_token)
        bot_info = await test_bot.get_me()
        await test_bot.close()
    except Exception as e:
        await msg.edit_text(f"❌ Invalid token!\nError: {e}")
        return

    db.set_setting("BOT_TOKEN", new_token)
    await msg.edit_text(f"✅ Token validated for @{bot_info.username}.\n\n🔄 Restarting bot...")
    await asyncio.sleep(2)
    os.execv(sys.executable, ['python'] + sys.argv)

async def status_clone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    clones = db.get_clones()
    if not clones:
        await update.message.reply_text("No clone bots found. Use `/clone <token>` to add one.")
        return

    kb = []
    for c in clones:
        kb.append([InlineKeyboardButton(f"📊 @{c['username']}", callback_data=f"statclone:{c['username']}")])
    
    await update.message.reply_text("🤖 <b>Bot Clones Dashboard</b>\n\nSelect a clone to view its stats:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def blocked_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    blocked = db.get_blocked_users()
    if not blocked:
        await update.message.reply_text("✅ No blocked users detected yet.")
        return
    
    text = "🚫 <b>BLOCKED USERS DETECTED</b>\n───────────────────────\n"
    for b in blocked[:20]:
        name = f"@{b['username']}" if b['username'] else "No Username"
        text += f"• {name} | <code>{b['telegram_id']}</code>\n  🕒 {_fmt_ts(b['blocked_at'])}\n"
    
    if len(blocked) > 20: text += f"\n<i>(Showing latest 20 of {len(blocked)} total)</i>"
    await update.message.reply_text(text, parse_mode="HTML")

async def status_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    try: target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Usage: `/status_user <user_id>`")
        return

    msg = await update.message.reply_text("🔍 Checking live Telegram status...")
    
    live_status = "⚪ Unknown"
    try:
        await context.bot.send_chat_action(chat_id=target_id, action="typing")
        live_status = "🟢 Live (Active)"
    except Forbidden:
        live_status = "🔴 Blocked (Bot cannot message user)"
        db.log_blocked_user(target_id)
    except BadRequest:
        live_status = "⚫ Deactivated / Not Found"

    summary = db.get_user_summary(target_id)
    db_text = "⚠️ User not found in database."
    if summary:
        name = summary.get('first_name') or "Unknown"
        uname = f"@{summary['username']}" if summary.get('username') else "None"
        db_text = (
            f"📛 Name: {name} ({uname})\n"
            f"📅 First Seen: {_fmt_ts(summary['first_seen'])}\n"
            f"🕒 Last Seen: {_fmt_ts(summary['last_seen'])}\n"
            f"📈 Actions: {summary['total_actions']}"
        )

    text = f"👤 <b>USER PROFILE: {target_id}</b>\n───────────────────────\n"
    text += f"<b>Live Status:</b> {live_status}\n\n"
    text += f"<b>Database Stats:</b>\n{db_text}"
    
    await msg.edit_text(text, parse_mode="HTML")

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    if not update.message.reply_to_message:
        await update.message.reply_text("⚠️ Reply to a message with /delete")
        return
    try:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=update.message.reply_to_message.message_id)
        await update.message.delete()
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to delete: {e}")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await _log(*_user_meta(update), "/admin", "opened admin", context.bot.username)
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

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    await _log(*_user_meta(update), "/status", "opened user list", context.bot.username)
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

async def skip_button_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    admin_id = update.effective_user.id
    state = BROADCAST_STATE.get(admin_id)
    
    if state and state["step"] == "waiting_for_button":
        state["step"] = "waiting_for_target"
        state["reply_markup"] = None
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 All Users", callback_data="bcast:users")],
            [InlineKeyboardButton("🎯 Specific Users", callback_data="bcast:specific")],
            [InlineKeyboardButton("👥 All Groups", callback_data="bcast:groups")],
            [InlineKeyboardButton("🎯 Specific Groups", callback_data="bcast:specific_groups")], # FIXED
            [InlineKeyboardButton("📢 All Channels", callback_data="bcast:channels")],
        ])
        await update.message.reply_text("✅ Setup complete.\n\n<b>Where do you want to send this?</b>", reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text("No active broadcast to skip button for.")

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    BROADCAST_STATE[update.effective_user.id] = {"step": "waiting_for_message", "bot_source": context.bot.username}
    await update.message.reply_text("📢 <b>Broadcast Mode</b>\n\nSend the message to broadcast. Send /cancel to abort.", parse_mode="HTML")

async def cancel_broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update): return
    BROADCAST_STATE.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Broadcast cancelled.")

async def execute_broadcast(progress_msg, broadcast_msg, chat_ids, target_name, context, reply_markup=None, broadcast_id=None):
    success = 0
    failed = 0
    status_msg = await progress_msg.reply_text(f"⏳ Progress: 0/{len(chat_ids)}")
    
    for index, chat_id in enumerate(chat_ids, 1):
        try:
            await broadcast_msg.copy(chat_id=chat_id, reply_markup=reply_markup)
            success += 1
            db.remove_blocked_user(chat_id) 
        except Forbidden as e:
            print(f"Forbidden to {chat_id}: {e}")
            failed += 1
            if "blocked by the user" in str(e).lower() or "deactivated" in str(e).lower():
                db.log_blocked_user(chat_id)
        except Exception as e:
            print(f"Failed to send to {chat_id}: {e}")
            failed += 1
        
        if index % 10 == 0 or index == len(chat_ids):
            try: await status_msg.edit_text(f"⏳ Progress: {index}/{len(chat_ids)}\n✅ Success: {success} | ❌ Failed: {failed}")
            except: pass
        await asyncio.sleep(0.1)

    text = f"🏁 <b>Broadcast Finished!</b>\n\n🎯 Target: {target_name}\n✅ Success: {success}\n❌ Failed: {failed}\n"
    kb = []
    if reply_markup and broadcast_id:
        text += "\n🔗 Click tracking is active for this broadcast."
        kb.append([InlineKeyboardButton("📊 View Click Analytics", callback_data=f"bcanalytics:{broadcast_id}")])
    
    try: await status_msg.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb) if kb else None)
    except: pass

# ==========================================================
# CALLBACKS
# ==========================================================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update): return
    data = query.data or ""
    admin_id = update.effective_user.id

    if data.startswith("bcanalytics:"):
        bid = data.split(":")[1]
        clicks = db.get_broadcast_clicks(bid)
        if not clicks:
            await query.message.reply_text("No clicks recorded yet for this broadcast.")
            return
        text = f"👆 <b>UNIQUE CLICKERS ({len(clicks)})</b>\n───────────────────────\n"
        for c in clicks[:20]:
            name = f"@{c['username']}" if c['username'] else "No Username"
            text += f"• {name} | <code>{c['telegram_id']}</code>\n  🕒 {_fmt_ts(c['clicked_at'])}\n"
        if len(clicks) > 20: text += f"\n<i>(Showing latest 20)</i>"
        await query.message.reply_text(text, parse_mode="HTML")
        return

    if data.startswith("statclone:"):
        bot_uname = data.split(":")[1]
        stats = db.get_clone_stats(bot_uname)
        groups = db.get_clone_groups(bot_uname)
        users = db.get_clone_latest_users(bot_uname, 20)
        
        text = f"📊 <b>Stats for @{bot_uname}</b>\n───────────────────────\n"
        text += f"👥 Total Users: {stats['users']}\n🏘 Total Groups: {stats['groups']}\n\n"
        
        if groups:
            text += "📢 <b>Groups:</b>\n"
            for g in groups: text += f"• {g['title']} (<code>{g['chat_id']}</code>)\n"
        
        if users:
            text += "\n👤 <b>Latest 20 Users:</b>\n"
            for u in users:
                uname = f"@{u['username']}" if u['username'] else u['first_name']
                text += f"• {uname} | <code>{u['telegram_id']}</code> | {_fmt_ts(u['last_seen'])}\n"
        
        await query.message.edit_text(text, parse_mode="HTML")
        return

    if data.startswith("bcast:"):
        state = BROADCAST_STATE.get(admin_id)
        if not state or "msg" not in state: return
        target = data.split(":")[1]
        reply_markup = state.get("reply_markup")
        bid = str(int(datetime.datetime.now().timestamp()))
        
        if target == "users":
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{BACKEND_URL}/api/admin/all-users")
                ids = r.json().get("users", [])
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> users...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], ids, "users", context, reply_markup, bid)
            BROADCAST_STATE.pop(admin_id, None)
        elif target == "groups":
            chats = db.get_tracked_chats(ChatType.GROUP) + db.get_tracked_chats(ChatType.SUPERGROUP)
            ids = [c["chat_id"] for c in chats]
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> groups...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], ids, "groups", context, reply_markup, bid)
            BROADCAST_STATE.pop(admin_id, None)
        elif target == "specific_groups": # FIXED
            state["step"] = "waiting_for_group_ids"
            await query.message.edit_text("🎯 <b>Specific Groups</b>\n\nSend the Group IDs separated by commas (e.g., <code>-1001234567890, -1009876543210</code>):", parse_mode="HTML")
        elif target == "channels":
            chats = db.get_tracked_chats(ChatType.CHANNEL)
            ids = [c["chat_id"] for c in chats]
            await query.message.edit_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> channels...", parse_mode="HTML")
            await execute_broadcast(query.message, state["msg"], ids, "channels", context, reply_markup, bid)
            BROADCAST_STATE.pop(admin_id, None)
        elif target == "specific":
            state["step"] = "waiting_for_ids"
            await query.message.edit_text("🎯 Send the Telegram IDs separated by commas:", parse_mode="HTML")
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
        await query.message.reply_text(f"✅ Approved request #{req_id}.")
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
    state = BROADCAST_STATE.get(admin_id)
    
    if state:
        if state["step"] == "waiting_for_message":
            state["msg"] = update.message
            state["step"] = "waiting_for_button"
            await update.message.reply_text("✅ Message received.\n\nDo you want to add an inline button?\nSend: <code>Button Text | https://yourlink.com</code>\n\nOr send /skip", parse_mode="HTML")
            return
        if state["step"] == "waiting_for_button":
            text = update.message.text or ""
            if "|" not in text:
                await update.message.reply_text("❌ Invalid format. Send <code>Button Text | https://yourlink.com</code> or /skip.", parse_mode="HTML")
                return
            btn_text, url = [x.strip() for x in text.split("|", 1)]
            
            bid = str(int(datetime.datetime.now().timestamp()))
            proxy_url = f"{BACKEND_URL}/api/click?bid={bid}&uid=0&uname=group&url={url}"
            
            if url == APP_URL or url.startswith("app:"):
                clean_url = url.replace("app:", "").rstrip('/')
                state["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, web_app=WebAppInfo(url=clean_url))]])
            else:
                state["reply_markup"] = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, url=proxy_url)]])
                
            state["step"] = "waiting_for_target"
            
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("👥 All Users", callback_data="bcast:users")],
                [InlineKeyboardButton("🎯 Specific Users", callback_data="bcast:specific")],
                [InlineKeyboardButton("👥 All Groups", callback_data="bcast:groups")],
                [InlineKeyboardButton("🎯 Specific Groups", callback_data="bcast:specific_groups")], # FIXED
                [InlineKeyboardButton("📢 All Channels", callback_data="bcast:channels")],
            ])
            await update.message.reply_text("✅ Button added with Click Tracking.\n\n<b>Where do you want to send this?</b>", reply_markup=kb, parse_mode="HTML")
            return

        if state["step"] == "waiting_for_ids":
            text = update.message.text.replace(" ", "")
            try: ids = [int(i.strip()) for i in text.split(",") if i.strip()]
            except ValueError: 
                await update.message.reply_text("❌ Invalid format.")
                return
            await update.message.reply_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> specific users...", parse_mode="HTML")
            bid = str(int(datetime.datetime.now().timestamp()))
            await execute_broadcast(update.message, state["msg"], ids, "specific users", context, state.get("reply_markup"), bid)
            BROADCAST_STATE.pop(admin_id, None)
            return

        if state["step"] == "waiting_for_group_ids": # FIXED
            text = update.message.text.replace(" ", "")
            try: ids = [int(i.strip()) for i in text.split(",") if i.strip()]
            except ValueError: 
                await update.message.reply_text("❌ Invalid format.")
                return
            await update.message.reply_text(f"🚀 Starting broadcast to <b>{len(ids)}</b> specific groups...", parse_mode="HTML")
            bid = str(int(datetime.datetime.now().timestamp()))
            await execute_broadcast(update.message, state["msg"], ids, "specific groups", context, state.get("reply_markup"), bid)
            BROADCAST_STATE.pop(admin_id, None)
            return

    req_id = AWAITING_OTP_FOR.get(update.effective_chat.id)
    if req_id:
        text = (update.message.text or "").strip()
        if len(text) != 6 or not text.isdigit():
            await update.message.reply_text("❌ Send exactly 6 digits.")
            return
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(f"{BACKEND_URL}/api/admin/assign", json={"request_id": req_id, "otp": text})
        AWAITING_OTP_FOR.pop(update.effective_chat.id, None)
        await update.message.reply_text(f"✅ OTP <code>{text}</code> saved for request #{req_id}.", parse_mode="HTML")

# ==========================================================
# MULTI-BOT SETUP AND RUNNER
# ==========================================================
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("cancel", cancel_broadcast_cmd))
    app.add_handler(CommandHandler("skip", skip_button_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("clone", clone_cmd))
    app.add_handler(CommandHandler("migrate", migrate_cmd))
    app.add_handler(CommandHandler("status_clone", status_clone_cmd))
    app.add_handler(CommandHandler("status_user", status_user_cmd))
    app.add_handler(CommandHandler("blocked", blocked_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, track_chats))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, text_handler))

async def run_bots():
    db.init_db()
    
    tokens = []
    main_token = db.get_setting("BOT_TOKEN") or os.getenv("BOT_TOKEN", "")
    if main_token:
        tokens.append(main_token)
    
    clones = db.get_clones()
    for c in clones:
        tokens.append(c["token"])

    if not tokens:
        print("CRITICAL: No bot tokens found.")
        return

    apps = []
    for token in tokens:
        app = (
            Application.builder().token(token)
            .connect_timeout(30.0).read_timeout(30.0).write_timeout(30.0).pool_timeout(30.0)
            .build()
        )
        register_handlers(app)
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        apps.append(app)
        print(f"Started bot with token ending in ...{token[-5:]}")

    print(f"✅ {len(apps)} Bot(s) are running...")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(run_bots())
    except (KeyboardInterrupt, SystemExit):
        print("Bot stopped.")
