import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler

# Получаем переменные окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN or not BASE_URL:
    raise RuntimeError("Переменные окружения TELEGRAM_TOKEN и BASE_URL обязательны!")

# Создаём Flask-приложение
app = Flask(__name__)

# Инициализация Telegram-приложения
application = ApplicationBuilder().token(TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context):
    await update.message.reply_text("Привет! Я работаю через Webhook.")

application.add_handler(CommandHandler("start", start))

# Установка webhook
@app.before_first_request
def set_webhook():
    url = f"{BASE_URL}/{TOKEN}"
    asyncio.run(application.bot.set_webhook(url))

# Приём входящих сообщений
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return "ok"

# Запуск Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
