import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)
import logging

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Flask
app = Flask(__name__)

# Переменные окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

# Telegram Application
application = ApplicationBuilder().token(BOT_TOKEN).build()

# /start команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот и уже работаю 🔥")

# Регистрируем хендлер
application.add_handler(CommandHandler("start", start))

# Инициализация бота и установка Webhook
async def init_bot():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logging.info("Бот запущен и Webhook установлен.")

# Webhook обработчик
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
    return "ok"

# При запуске контейнера
@app.before_first_request
def before_first_request():
    asyncio.run(init_bot())
