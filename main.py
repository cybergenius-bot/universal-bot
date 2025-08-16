import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

TOKEN = os.getenv("BOT_TOKEN")  # ⚠️ переменная окружения в Railway
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Функция для отправки сообщения
def send_message(chat_id: int, text: str):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# Корневой маршрут для проверки
@app.get("/")
def home():
    return {"status": "ok", "message": "Bot is running on Railway!"}

# Webhook endpoint
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Реакции без "попугая"
        if text == "/start":
            send_message(chat_id, "Привет! 🤖 Я твой бот. Напиши команду, и я помогу.")
        elif text.lower() in ["привет", "hello", "shalom"]:
            send_message(chat_id, "Приветствую! 👋 Рад тебя видеть.")
        elif text == "/help":
            send_message(chat_id, "Доступные команды:\n/start - начать\n/help - помощь")
        else:
            send_message(chat_id, "Я пока не понял твою команду 🙈. Напиши /help.")

    return {"ok": True}
