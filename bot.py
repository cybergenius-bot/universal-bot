import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Получаем переменные окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")

# Проверка токена и URL
if not TOKEN or not BASE_URL:
    raise RuntimeError("Переменные окружения TELEGRAM_TOKEN и BASE_URL обязательны!")

# Создаём Flask
app = Flask(__name__)

# Создаём Telegram Application
application = Application.builder().token(TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я CyberGenius 🤖 Готов помочь!")

# Регистрируем handler
application.add_handler(CommandHandler("start", start))

# Webhook endpoint — исправлено на PTB-safe метод
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.create_task(application.process_update(update))  # 💡 Вот правильное место
    except Exception as e:
        print(f"[ERROR] Ошибка в webhook: {e}")
    return "OK", 200

# Устанавливаем Webhook до запуска Flask
async def setup():
    await application.initialize()
    webhook_url = f"{BASE_URL}/{TOKEN}"
    await application.bot.set_webhook(url=webhook_url)
    print(f"[INFO] Webhook установлен: {webhook_url}")

if __name__ == "__main__":
    asyncio.run(setup())
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
