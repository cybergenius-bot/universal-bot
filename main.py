import os
import httpx
from fastapi import FastAPI, Request

TOKEN = os.getenv("BOT_TOKEN", "8091774335:AAFTHo_xWA0kpAV_CK4BdyWMq2K3Sbg_GaQ")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TOKEN:
        return {"error": "Invalid token"}

    data = await request.json()
    print("🔹 Update:", data)  

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").lower()

        # ====== ЛОГИКА ОТВЕТОВ ======
        if "привет" in text:
            reply = "Привет! 👋 Как у тебя дела?"
        elif "как дела" in text:
            reply = "У меня всё отлично, работаю 24/7 🚀. А у тебя?"
        elif "пока" in text:
            reply = "До встречи! 👋"
        else:
            reply = "Я тебя понял. Продолжай 😉"

        # Отправляем ответ
        async with httpx.AsyncClient() as client:
            r = await client.post(f"{BASE_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": reply
            })
            print("🔹 Telegram API response:", r.json())

    return {"ok": True}
