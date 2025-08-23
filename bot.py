from flask import Flask, request
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler
import os

app = Flask(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = os.getenv("BASE_URL")

if not TOKEN or not BASE_URL:
    raise RuntimeError("TELEGRAM_TOKEN и BASE_URL обязательны")

application = Application.builder().token(TOKEN).build()

# Обработчик команды /start
async def start(update: Update, context):
    await update.message.reply_text("Привет! Бот работает ✅")

application.add_handler(CommandHandler("start", start))

# Webhook endpoint
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.process_update(update))
    return "OK", 200

# Установка Webhook
@app.before_first_request
def setup():
    url = f"{BASE_URL}/{TOKEN}"
    asyncio.get_event_loop().run_until_complete(application.bot.set_webhook(url=url))
