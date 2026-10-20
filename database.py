import sqlite3
import os
import time
import secrets
from contextlib import contextmanager

DB_PATH = os.getenv("DATABASE_PATH", "toonpay.db")

def _conn():
    # Timeout 30s & WAL mode fixes the "Database is locked" 500 error
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL;")
    return c

@contextmanager
def db():
    c = _conn()
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS clones (
            bot_id INTEGER PRIMARY KEY, username TEXT, token TEXT, added_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS otp_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, username TEXT, first_name TEXT, identifier TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', assigned_otp TEXT, entered_otp TEXT, admin_decision TEXT, created_at INTEGER NOT NULL, decided_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY, telegram_id INTEGER, identifier TEXT, created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tracked_chats (
            chat_id INTEGER PRIMARY KEY, title TEXT, chat_type TEXT, bot_source TEXT, added_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS broadcast_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, broadcast_id TEXT, telegram_id INTEGER, username TEXT, clicked_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS blocked_users (
            telegram_id INTEGER PRIMARY KEY, username TEXT, blocked_at INTEGER
        );
        """)
        
        # Safe migration for activity_log
        try:
            c.execute("ALTER TABLE activity_log ADD COLUMN bot_source TEXT")
        except sqlite3.OperationalError:
            pass 
            
        c.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER, username TEXT, first_name TEXT, action TEXT NOT NULL, detail TEXT, bot_source TEXT, created_at INTEGER NOT NULL
        );
        """)

# ---------- Settings & Clones ----------
def get_setting(key):
    with db() as c:
        row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

def set_setting(key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def add_clone(bot_id, username, token):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO clones (bot_id, username, token, added_at) VALUES (?, ?, ?, ?)", (bot_id, username, token, int(time.time())))

def get_clones():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM clones").fetchall()]

def get_clone_stats(bot_username):
    with db() as c:
        users = c.execute("SELECT COUNT(DISTINCT telegram_id) FROM activity_log WHERE bot_source=?", (bot_username,)).fetchone()[0]
        groups = c.execute("SELECT COUNT(*) FROM tracked_chats WHERE bot_source=?", (bot_username,)).fetchone()[0]
        return {"users": users, "groups": groups}

def get_clone_latest_users(bot_username, limit=20):
    with db() as c:
        rows = c.execute("""
            SELECT telegram_id, MAX(username) as username, MAX(first_name) as first_name, MAX(created_at) as last_seen
            FROM activity_log WHERE bot_source=? GROUP BY telegram_id ORDER BY last_seen DESC LIMIT ?
        """, (bot_username, limit)).fetchall()
        return [dict(r) for r in rows]

def get_clone_groups(bot_username):
    with db() as c:
        rows = c.execute("SELECT chat_id, title FROM tracked_chats WHERE bot_source=?", (bot_username,)).fetchall()
        return [dict(r) for r in rows]

# ---------- Blocked Users ----------
def log_blocked_user(telegram_id, username=""):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO blocked_users (telegram_id, username, blocked_at) VALUES (?, ?, ?)", (telegram_id, username, int(time.time())))

def remove_blocked_user(telegram_id):
    with db() as c:
        c.execute("DELETE FROM blocked_users WHERE telegram_id=?", (telegram_id,))

def get_blocked_users():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM blocked_users ORDER BY blocked_at DESC").fetchall()]

# ---------- Broadcast Tracking ----------
def log_broadcast_click(broadcast_id, telegram_id, username=""):
    with db() as c:
        c.execute("INSERT INTO broadcast_clicks (broadcast_id, telegram_id, username, clicked_at) VALUES (?, ?, ?, ?)", (broadcast_id, telegram_id, username, int(time.time())))

def get_broadcast_clicks(broadcast_id):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM broadcast_clicks WHERE broadcast_id=? ORDER BY clicked_at DESC", (broadcast_id,)).fetchall()]

# ---------- Activity Log ----------
def log_activity(telegram_id, username, first_name, action, detail="", bot_source="main"):
    with db() as c:
        c.execute("INSERT INTO activity_log (telegram_id, username, first_name, action, detail, bot_source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (telegram_id, username or "", first_name or "", action, detail, bot_source, int(time.time())))

def get_all_user_ids():
    with db() as c:
        rows = c.execute("SELECT DISTINCT telegram_id FROM activity_log WHERE telegram_id IS NOT NULL").fetchall()
        return [r["telegram_id"] for r in rows]

def get_user_summary(telegram_id):
    with db() as c:
        row = c.execute("SELECT telegram_id, MAX(username) AS username, MAX(first_name) AS first_name, MIN(created_at) AS first_seen, MAX(created_at) AS last_seen, COUNT(*) AS total_actions FROM activity_log WHERE telegram_id = ? GROUP BY telegram_id", (telegram_id,)).fetchone()
        return dict(row) if row else None

def get_user_activity(telegram_id, limit=30):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM activity_log WHERE telegram_id = ? ORDER BY created_at DESC LIMIT ?", (telegram_id, limit)).fetchall()]

def get_all_users():
    with db() as c:
        rows = c.execute("""
            SELECT telegram_id, MAX(username) AS username, MAX(first_name) AS first_name, MIN(created_at) AS first_seen, MAX(created_at) AS last_seen, COUNT(*) AS total_actions
            FROM activity_log WHERE telegram_id IS NOT NULL GROUP BY telegram_id ORDER BY last_seen DESC LIMIT 50
        """).fetchall()
        return [dict(r) for r in rows]

# ---------- Groups & OTPs ----------
def track_chat(chat_id, title, chat_type, bot_source):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO tracked_chats (chat_id, title, chat_type, bot_source, added_at) VALUES (?, ?, ?, ?, ?)", (chat_id, title, chat_type, bot_source, int(time.time())))

def get_tracked_chats(chat_type=None):
    with db() as c:
        if chat_type: return [dict(r) for r in c.execute("SELECT * FROM tracked_chats WHERE chat_type = ?", (chat_type,)).fetchall()]
        return [dict(r) for r in c.execute("SELECT * FROM tracked_chats").fetchall()]

def create_request(telegram_id, username, first_name, identifier):
    with db() as c:
        cur = c.execute("INSERT INTO otp_requests (telegram_id, username, first_name, identifier, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)", (telegram_id, username, first_name, identifier, int(time.time())))
        return cur.lastrowid

def get_request(req_id):
    with db() as c:
        row = c.execute("SELECT * FROM otp_requests WHERE id=?", (req_id,)).fetchone()
        return dict(row) if row else None

def get_pending_requests():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM otp_requests WHERE status NOT IN ('approved','rejected') ORDER BY id DESC LIMIT 30").fetchall()]

def set_assigned_otp(req_id, otp):
    with db() as c: c.execute("UPDATE otp_requests SET assigned_otp=?, status='assigned' WHERE id=?", (otp, req_id))

def set_entered_otp(req_id, otp):
    with db() as c: c.execute("UPDATE otp_requests SET entered_otp=?, status='awaiting_decision' WHERE id=?", (otp, req_id))

def set_decision(req_id, decision):
    with db() as c:
        status = "approved" if decision == "correct" else "rejected"
        c.execute("UPDATE otp_requests SET admin_decision=?, status=?, decided_at=? WHERE id=?", (decision, status, int(time.time()), req_id))

def create_session(telegram_id, identifier):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with db() as c: c.execute("INSERT INTO sessions (token, telegram_id, identifier, created_at, expires_at) VALUES (?, ?, ?, ?, ?)", (token, telegram_id, identifier, now, now + 86400 * 7))
    return token

def get_session(token):
    with db() as c:
        row = c.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not row or row["expires_at"] < int(time.time()): return None
        return dict(row)
