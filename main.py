import os
from fastapi import FastAPI, Request
import requests

TOKEN = os.getenv("BOT_TOKEN")  # токен из Railway Variables
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

@app.get("/")
def home():
    return {"status": "ok"}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TOKEN:
        return {"ok": False, "error": "Invalid token"}

    data = await request.json()
    print("Incoming update:", data)

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Вы написали: {text}"
        })

    return {"ok": True}

