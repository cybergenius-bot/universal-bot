import os
import logging
from fastapi import FastAPI, Request
from telegram.ext import ApplicationBuilder
from telegram import Update

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TOKEN")  # В Railway в переменных окружения
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://{os.getenv('RAILWAY_STATIC_URL')}{WEBHOOK_PATH}"

app = FastAPI()

# Создаём приложение Telegram
application = ApplicationBuilder().token(TOKEN).build()

# Простой обработчик для теста
async def start(update: Update, context):
    await update.message.reply_text("Бот работает!")

application.add_handler(CommandHandler("start", start))

@app.on_event("startup")
async def on_startup():
    logger.info(f"Запуск бота, установка вебхука: {WEBHOOK_URL}")
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.start()

@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Остановка бота...")
    await application.stop()

@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
