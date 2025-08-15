import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Читаем токен из переменных окружения
TOKEN = os.getenv("TOKEN")  # В Railway в Variables должно быть TOKEN=твой_токен

app = FastAPI()

# Создаём приложение Telegram
application = ApplicationBuilder().token(TOKEN).build()

# Простой хэндлер для /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот запущен и работает ✅")

application.add_handler(CommandHandler("start", start))

# Маршрут для вебхука
@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"ok": True}

# При старте приложения — установка вебхука
@app.on_event("startup")
async def startup_event():
    webhook_url = "https://universal-bot-production.up.railway.app/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")

# Запуск Telegram Application в фоне
@app.on_event("startup")
async def run_bot():
    await application.start()

@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()
