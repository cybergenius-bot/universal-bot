import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не найден BOT_TOKEN в переменных окружения!")

app = FastAPI()
application = Application.builder().token(TOKEN).build()

# --- Команды ---
async def start(update: Update, context):
    await update.message.reply_text("Привет! Я бот, могу общаться с тобой 🙂")

async def help_command(update: Update, context):
    await update.message.reply_text("Напиши мне сообщение — я отвечу не как попугай 🦜, а как собеседник!")

# --- Общение ---
async def chat_handler(update: Update, context):
    text = update.message.text.lower()

    if "привет" in text:
        reply = "Привет 👋 Как настроение?"
    elif "как дела" in text:
        reply = "У меня всё отлично, спасибо! А у тебя?"
    elif "что делаешь" in text:
        reply = "С тобой переписываюсь 😉"
    elif "пока" in text:
        reply = "До скорого! 👋"
    elif "кто ты" in text:
        reply = "Я Telegram-бот, живу на Railway 🚂"
    else:
        reply = "Хм 🤔 интересно, расскажи больше!"

    await update.message.reply_text(reply)

# --- Handlers ---
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
