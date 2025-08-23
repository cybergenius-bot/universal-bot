import os
import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes


# Переменные окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")
PORT = int(os.getenv("PORT", 5000))


# Проверка
if not TOKEN or not BASE_URL:
raise RuntimeError("Переменные окружения TELEGRAM_TOKEN и BASE_URL обязательны!")


# Flask и Telegram Application
app = Flask(__name__)
application = Application.builder().token(TOKEN).build()


# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! Я CyberGenius 🤖 Готов помочь!")


application.add_handler(CommandHandler("start", start))


# Webhook endpoint (sync-функция для Flask)
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
try:
update = Update.de_json(request.get_json(force=True), application.bot)
asyncio.create_task(application.process_update(update))
except Exception as e:
print(f"[ERROR] Webhook error: {e}")
return "OK", 200


# Установка Webhook
async def setup():
await application.initialize()
webhook_url = f"{BASE_URL}/{TOKEN}"
await application.bot.set_webhook(url=webhook_url)
print(f"[INFO] Webhook установлен: {webhook_url}")


# Запуск
if __name__ == "__main__":
asyncio.run(setup())
app.run(host="0.0.0.0", port=PORT)
