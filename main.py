import os
from fastapi import FastAPI, Request

TOKEN = os.getenv("TELEGRAM_TOKEN")  # на всякий случай, вдруг будем проверять позже
WEBHOOK_PATH = "/webhook"

app = FastAPI()

# Проверка сервера
@app.get("/")
async def root():
    return {"status": "ok"}

# Минимальный обработчик вебхука
@app.post(WEBHOOK_PATH)
async def process_webhook(request: Request):
    data = await request.json()
    print("📩 Пришло от Telegram:", data)  # Логируем апдейт в Railway Logs
    return {"ok": True}
