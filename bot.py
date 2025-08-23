import os
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
import asyncio
import logging

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Flask-приложение
app = Flask(__name__)

# Получение переменных окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # например, https://your-app.up.railway.app

# Telegram Application
application = ApplicationBuilder().token(BOT_TOKEN).build()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот и уже работаю 🔥")

# Регистрация хендлеров
application.add_handler(CommandHandler("start", start))

# Инициализация
async def init_bot():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logging.info("Бот инициализирован и Webhook установлен.")

# Webhook маршрут
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.process_update(update))
    return "ok"

# Запуск и инициализация бота при старте сервера
@app.before_first_request
def before_first_request():
    asyncio.run(init_bot())
