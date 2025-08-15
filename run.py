import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаём FastAPI приложение
app = FastAPI()

# Получаем токен бота из переменных окружения
TOKEN = os.getenv("TOKEN")

# Создаём Telegram Application
application = ApplicationBuilder().token(TOKEN).build()

# Стартовое событие
@app.on_event("startup")
async def on_startup():
    logger.info("Запуск приложения...")
    # Устанавливаем вебхук
    webhook_url = f"https://{os.getenv('RAILWAY_STATIC_URL')}/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")

# Событие остановки
@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Остановка приложения...")
    await application.stop()

# Обработка запросов от Telegram
@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# Для проверки работоспособности
@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running"}
