from fastapi import FastAPI, Request
import requests
import os

TOKEN = os.getenv("BOT_TOKEN")  # твой токен бота в Railway Variables
API_URL = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

# обработка вебхука именно по /webhook/{token}
@app.post(f"/webhook/{TOKEN}")
async def webhook_handler(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        # отвечаем текстом
        requests.post(f"{API_URL}/sendMessage", json={"chat_id": chat_id, "text": f"Вы написали: {text}"})
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "ok"}
