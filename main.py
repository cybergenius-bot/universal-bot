import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")

if not BOT_TOKEN or not RAILWAY_URL:
    raise ValueError("BOT_TOKEN и RAILWAY_URL должны быть заданы в переменных среды!")

# Создаём Telegram Application
application = Application.builder().token(BOT_TOKEN).build()

# Обработчики
async def start(update: Update, context):
    await update.message.reply_text("✅ Привет! Бот работает.")

async def echo(update: Update, context):
    await update.message.reply_text(f"Вы написали: {update.message.text}")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Создаём FastAPI
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await application.initialize()
    webhook_url = f"{RAILWAY_URL}/webhook/{BOT_TOKEN}"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

@app.post(f"/webhook/{BOT_TOKEN}")
async def handle_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def home():
    return {"status": "бот запущен"}
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "бот запущен"}
