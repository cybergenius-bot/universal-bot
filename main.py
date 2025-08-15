import os
from fastapi import FastAPI, Request
import requests

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

app = FastAPI()

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = "Привет! Бот успешно работает ✅"
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": text})
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "Bot is running"}
