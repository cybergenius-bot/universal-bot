import os
import requests
from fastapi import FastAPI, Request

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена!")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

@app.post(f"/webhook/{TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    print("📩 Получено:", data)

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]

        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Вы написали: {text}"
        })

    return {"ok": True}
