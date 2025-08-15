import os
from fastapi import FastAPI, Request
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")  # в Railway указываешь BOT_TOKEN
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # в Railway указываешь URL Railway + /webhook

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не установлен!")

app = FastAPI()
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Устанавливаем вебхук при старте
@app.on_event("startup")
def set_webhook():
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL не установлен!")
    r = requests.get(f"{TELEGRAM_API}/setWebhook", params={"url": WEBHOOK_URL + "/webhook"})
    print(r.json())

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        send_message(chat_id, f"Вы написали: {text}")
    return {"ok": True}

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

@app.get("/")
def home():
    return {"status": "бот работает"}
