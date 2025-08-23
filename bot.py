import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Получаем переменные окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN or not BASE_URL:
    raise RuntimeError("Переменные окружения TELEGRAM_TOKEN и BASE_URL обязательны!")

# Создаём Flask-приложение
app = Flask(__name__)

# Создаём Telegram Application
application = Application.builder().token(TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я CyberGenius 🤖 Готов помочь!")

# Регистрируем handler
application.add_handler(CommandHandler("start", start))

# Webhook endpoint (Flask получает обновления от Telegram)
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.create_task(application.process_update(update))
    return "OK", 200

# Установка Webhook перед запуском сервера
async def setup():
    await application.initialize()
    await application.bot.set_webhook(url=f"{BASE_URL}/{TOKEN}")
    print(f"[INFO] Webhook установлен: {BASE_URL}/{TOKEN}")

if __name__ == "__main__":
    asyncio.run(setup())
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
