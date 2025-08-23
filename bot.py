import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Чтение переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN or not BASE_URL:
    raise RuntimeError("TELEGRAM_TOKEN и BASE_URL обязательны")

# Flask-приложение
app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает! Добро пожаловать.")

application.add_handler(CommandHandler("start", start))

# Webhook для Telegram
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)

    async def process():
        if not application.ready:
            await application.initialize()
        await application.process_update(update)

    asyncio.run(process())
    return "OK", 200

# Установка Webhook при первом запуске
@app.before_first_request
def setup_webhook():
    async def set_webhook():
        await application.bot.set_webhook(url=f"{BASE_URL}/{TOKEN}")
        print(f"[INFO] Webhook установлен: {BASE_URL}/{TOKEN}")
    asyncio.run(set_webhook())
