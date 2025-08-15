import os
from fastapi import FastAPI, Request
import requests

TOKEN = os.getenv("BOT_TOKEN")  # Токен из переменных окружения Railway
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

# Главная страница
@app.get("/")
def home():
    return {"status": "ok"}

# Вебхук
@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TOKEN:
        return {"ok": False, "error": "Invalid token"}

    data = await request.json()
    print("Incoming update:", data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text.lower() in ["/start", "start"]:
            send_welcome(chat_id)
        elif text == "🏗 Стройка":
            send_text(chat_id, "Вы выбрали категорию: Стройка 🏗")
        elif text == "❤️ Отношения":
            send_text(chat_id, "Вы выбрали категорию: Отношения ❤️")
        elif text == "💼 Бизнес":
            send_text(chat_id, "Вы выбрали категорию: Бизнес 💼")
        elif text == "📷 Фото":
            send_photo(chat_id)
        else:
            send_text(chat_id, f"Вы написали: {text}")

    return {"ok": True}

# Отправка приветствия с кнопками
def send_welcome(chat_id):
    text = "Привет! Hello! שלום!\nВыберите категорию:"
    keyboard = {
        "keyboard": [
            ["🏗 Стройка", "❤️ Отношения"],
            ["💼 Бизнес", "📷 Фото"]
        ],
        "resize_keyboard": True
    }
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text,
        "reply_markup": keyboard
    })

# Отправка текста
def send_text(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })

# Отправка фото
def send_photo(chat_id):
    photo_url = "https://upload.wikimedia.org/wikipedia/commons/9/99/Sample_User_Icon.png"
    caption = "Это тестовое фото 📷"
    requests.post(f"{TELEGRAM_API}/sendPhoto", json={
        "chat_id": chat_id,
        "photo": photo_url,
        "caption": caption
  
