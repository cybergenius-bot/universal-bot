import os
import requests
from fastapi import FastAPI, Request

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

app = FastAPI()

def send_message(chat_id: int, text: str):
    requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text})

@app.get("/")
def home():
    return {"status": "Bot is running"}

@app.post(f"/webhook/{BOT_TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        send_message(chat_id, f"Вы написали: {text}")
    return {"ok": True}
