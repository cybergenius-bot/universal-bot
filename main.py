import os
import requests
from fastapi import FastAPI, Request

app = FastAPI()

TOKEN = os.getenv("BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Обработка команд
        if text == "/start":
            send_message(chat_id, "👋 Привет! Я твой бот. Можешь писать мне вопросы.")
        elif "привет" in text.lower():
            send_message(chat_id, "Привет! Как дела?")
        elif "как дела" in text.lower():
            send_message(chat_id, "У меня всё отлично, спасибо! 😊 А у тебя?")
        else:
            send_message(chat_id, f"Ты написал: {text}")

    return {"ok": True}
