# main.py
from fastapi import FastAPI, Request
import os
import requests

# Загружаем токен из переменных окружения Railway
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден в переменных окружения!")

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

# Создаём приложение FastAPI
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "Bot is running"}

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        return {"ok": False, "error": "Invalid token in URL"}
    
    data = await request.json()

    # Если пришло сообщение от пользователя
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text_in = data["message"].get("text", "")
        
        # Ответ пользователю
        reply_text = f"Вы написали: {text_in}"
        requests.post(f"{API_URL}/sendMessage", json={
            "chat_id": chat_id,
            "text": reply_text
        })

    return {"ok": True}
