import os
import requests
from fastapi import FastAPI, Request

TOKEN = os.getenv("TELEGRAM_TOKEN")  # В Railway переменная TELEGRAM_TOKEN = твой токен
if not TOKEN:
    raise RuntimeError("Переменная TELEGRAM_TOKEN не установлена!")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()


def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)


@app.post(f"/webhook/{TOKEN}")
async def webhook_handler(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        send_message(chat_id, f"Вы написали: {text}")
    return {"ok": True}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway подставит свой порт
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=port)
