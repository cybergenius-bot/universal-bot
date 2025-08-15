import os
import requests
from fastapi import FastAPI, Request

# Читаем токен из переменных окружения Railway
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения Railway!")

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()


@app.get("/")
def home():
    return {"status": "ok"}


@app.post(f"/webhook/{TOKEN}")
async def webhook(request: Request):
    data = await request.json()
    print("Incoming update:", data)

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]

        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Вы написали: {text}"
        })

    return {"ok": Tru

        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Вы написали: {text}"
        })

    return {"ok": True}
