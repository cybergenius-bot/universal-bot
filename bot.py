import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler

# Загружаем переменные окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN or not BASE_URL:
    raise RuntimeError("Переменные окружения TELEGRAM_TOKEN и BASE_URL обязательны!")

# Инициализируем Flask и Telegram Application
app = Flask(__name__)
application = ApplicationBuilder().token(TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context):
    await update.message.reply_text("Привет! Я работаю через Webhook.")

application.add_handler(CommandHandler("start", start))

# Обработка входящего Webhook
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return "ok"

# Установка Webhook и запуск Flask-сервера
if __name__ == "__main__":
    asyncio.run(application.bot.set_webhook(f"{BASE_URL}/{TOKEN}"))
    app.run(host="0.0.0.0", port=8080)
