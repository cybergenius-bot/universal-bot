import os
import requests
from fastapi import FastAPI, Request

# Читаем токен бота из переменной окружения
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Переменная окружения BOT_TOKEN не установлена!")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

def send_message(chat_id: int, text: str):
    """Отправка сообщения пользователю"""
    url = f"{TELEGRAM_API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Обработка входящих апдейтов"""
    data = await request.json()
    print("Update:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text == "/start":
            send_message(chat_id, "Привет! Я работаю 🚀")
        elif text:
            send_message(chat_id, f"Вы написали: {text}")

    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "ok"}
