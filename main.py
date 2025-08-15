import os
from fastapi import FastAPI, Request
import requests

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена!")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

@app.post(f"/webhook/{TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        send_message(chat_id, f"Вы написали: {text}")
    return {"ok": True}

def send_message(chat_id, text):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)
