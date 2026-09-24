import asyncio,os,httpx
from dotenv import load_dotenv
from aiogram import Bot,Dispatcher,F
from aiogram.filters import CommandStart
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,WebAppInfo
load_dotenv()
BOT_TOKEN=os.getenv("BOT_TOKEN","")
ADMIN_ID=int(os.getenv("ADMIN_TELEGRAM_ID","0"))
APP_URL=os.getenv("APP_URL","")
bot=Bot(BOT_TOKEN)
dp=Dispatcher()
@dp.message(CommandStart())
async def start(m:Message):
    if not APP_URL.startswith("https://"):
        await m.answer("👋 Welcome to ToonPay!\n\nConfigure APP_URL with your HTTPS Mini App URL first.")
        return
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Open ToonPay 🚀",web_app=WebAppInfo(url=APP_URL))]])
    await m.answer("👋 Welcome to ToonPay!\n\nTap below to open the ToonPay test dashboard.",reply_markup=kb)
async def admin_action(c:CallbackQuery,ok:bool):
    if c.from_user.id!=ADMIN_ID:
        await c.answer("Admin only.",show_alert=True); return
    rid=int(c.data.split(":")[1]); endpoint="approve" if ok else "reject"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r=await client.post(f"http://127.0.0.1:8000/internal/admin/{endpoint}/{rid}",headers={"X-Admin-ID":str(ADMIN_ID)})
        if r.status_code!=200:
            await c.answer("Backend error.",show_alert=True); return
        await c.answer("OTP approved ✅" if ok else "OTP rejected ❌")
        suffix="\n\n━━━━━━━━━━━━━━\n✅ OTP APPROVED\nUser can now enter ToonPay." if ok else "\n\n━━━━━━━━━━━━━━\n❌ OTP REJECTED\nUser must try again."
        await c.message.edit_text(c.message.text+suffix)
    except Exception:
        await c.answer("Backend is not reachable.",show_alert=True)
@dp.callback_query(F.data.startswith("otp_ok:"))
async def ok(c): await admin_action(c,True)
@dp.callback_query(F.data.startswith("otp_bad:"))
async def bad(c): await admin_action(c,False)
async def main():
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN is missing.")
    print("ToonPay Telegram bot running...")
    await dp.start_polling(bot)
if __name__=="__main__": asyncio.run(main())
