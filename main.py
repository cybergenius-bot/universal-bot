import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import logging

# Логирование (чтобы видеть ошибки в Railway логах)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не найден BOT_TOKEN в переменных окружения!")

app = FastAPI()
application = Application.builder().token(TOKEN).build()

# --- Логика команд ---
async def start(update: Update, context):
    await update.message.reply_text("Привет! Я бот для общения. Напиши что-нибудь 🙂")

async def help_command(update: Update, context):
    await update.message.reply_text("Я могу переписываться с тобой. Просто напиши сообщение!")

# --- Логика переписки ---
async def chat_handler(update: Update, context):
    text = update.message.text.lower()

    if "привет" in text:
        reply = "Привет 👋 Как у тебя дела?"
    elif "как дела" in text:
        reply = "У меня всё отлично, спасибо что спросил!"
    elif "пока" in text:
        reply = "До встречи! 👋"
    elif "кто ты" in text:
        reply = "Я твой Telegram-бот, созданный на Railway 🚂"
    else:
        reply = "Интересно 🤔 расскажи подробнее."

    await update.message.reply_text(reply)

# --- Подключение хендлеров ---
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

# --- Webhook ---
@app.post("/webhook/{token}")
async def webhook(request: Request, token: str):
    if token == TOKEN:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.initialize()
        await application.process_update(update)
        return {"ok": True}
    return {"error": "invalid token"}
