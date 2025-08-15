import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler
import logging

# Логи для отладки
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TOKEN = os.getenv("BOT_TOKEN")  # Токен бота из Railway Variables
RAILWAY_URL = os.getenv("RAILWAY_URL")  # Например: https://universal-bot-production.up.railway.app

# Создаём приложение Telegram
application = Application.builder().token(TOKEN).build()

# Создаём FastAPI сервер
app = FastAPI()

# Команда /start
async def start(update: Update, context):
    await update.message.reply_text("✅ Бот запущен и готов к работе!")

application.add_handler(CommandHandler("start", start))

# При старте сервера
@app.on_event("startup")
async def startup_event():
    await application.initialize()
    webhook_url = f"{RAILWAY_URL}/webhook/{TOKEN}"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

# Обработка вебхуков
@app.post(f"/webhook/{TOKEN}")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# При завершении работы
@app.on_event("shutdown")
async def shutdown_event():
    await application.shutdown()
