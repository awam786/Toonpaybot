import os
import secrets
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = os.getenv("DATABASE_PATH", "toonpay_demo.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS login_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            login_value TEXT NOT NULL,
            login_method TEXT NOT NULL,
            demo_code_hash TEXT,
            code_configured INTEGER NOT NULL DEFAULT 0,
            code_verified INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'waiting_code',
            session_token TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            session_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def now():
    return datetime.now(timezone.utc).isoformat()


def create_login_request(
    telegram_id: int,
    username: str | None,
    login_value: str,
    login_method: str,
):
    conn = get_connection()
    timestamp = now()

    cursor = conn.execute(
        """
        INSERT INTO login_requests (
            telegram_id,
            username,
            login_value,
            login_method,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, 'waiting_code', ?, ?)
        """,
        (
            telegram_id,
            username,
            login_value,
            login_method,
            timestamp,
            timestamp,
        ),
    )

    request_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return request_id


def get_request(request_id: int):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM login_requests
        WHERE id = ?
        """,
        (request_id,),
    ).fetchone()

    conn.close()
    return row


def set_demo_code(request_id: int, code_hash: str):
    conn = get_connection()

    conn.execute(
        """
        UPDATE login_requests
        SET
            demo_code_hash = ?,
            code_configured = 1,
            status = 'waiting_user_code',
            updated_at = ?
        WHERE id = ?
        """,
        (
            code_hash,
            now(),
            request_id,
        ),
    )

    conn.commit()
    conn.close()


def mark_code_verified(request_id: int):
    conn = get_connection()

    conn.execute(
        """
        UPDATE login_requests
        SET
            code_verified = 1,
            status = 'approved',
            updated_at = ?
        WHERE id = ?
        """,
        (
            now(),
            request_id,
        ),
    )

    conn.commit()
    conn.close()


def mark_code_rejected(request_id: int):
    conn = get_connection()

    conn.execute(
        """
        UPDATE login_requests
        SET
            code_verified = 0,
            status = 'rejected',
            updated_at = ?
        WHERE id = ?
        """,
        (
            now(),
            request_id,
        ),
    )

    conn.commit()
    conn.close()


def set_status(request_id: int, status: str):
    conn = get_connection()

    conn.execute(
        """
        UPDATE login_requests
        SET
            status = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            status,
            now(),
            request_id,
        ),
    )

    conn.commit()
    conn.close()


def create_session(telegram_id: int, username: str | None):
    token = secrets.token_urlsafe(32)

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO sessions (
            telegram_id,
            username,
            session_token,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            telegram_id,
            username,
            token,
            now(),
        ),
    )

    conn.commit()
    conn.close()

    return token


def get_session(session_token: str):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM sessions
        WHERE session_token = ?
        """,
        (session_token,),
    ).fetchone()

    conn.close()
    return row


def attach_session(request_id: int, session_token: str):
    conn = get_connection()

    conn.execute(
        """
        UPDATE login_requests
        SET
            session_token = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            session_token,
            now(),
            request_id,
        ),
    )

    conn.commit()
    conn.close()
