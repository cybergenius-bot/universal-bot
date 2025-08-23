import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Получаем токен и базовый URL
TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN or not BASE_URL:
    raise RuntimeError("Переменные окружения TELEGRAM_TOKEN и BASE_URL обязательны!")

# Инициализируем Flask
app = Flask(__name__)

# Создаём Telegram Application
application = Application.builder().token(TOKEN).build()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я CyberGenius 🤖 Готов помочь!")

# Регистрируем handler
application.add_handler(CommandHandler("start", start))

# Webhook endpoint
@app.post(f"/{TOKEN}")
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        asyncio.run(application.process_update(update))
    except Exception as e:
        print(f"[ERROR] Ошибка во время обработки webhook: {e}")
    return "ok", 200

# Устанавливаем webhook перед запуском сервера
async def setup():
    await application.initialize()
    webhook_url = f"{BASE_URL}/{TOKEN}"
    await application.bot.set_webhook(url=webhook_url)
    print(f"[INFO] Webhook установлен: {webhook_url}")

if __name__ == "__main__":
    asyncio.run(setup())
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
