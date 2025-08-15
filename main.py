import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import logging

# --- Логирование ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Переменные ---
TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")

if not TOKEN or not RAILWAY_URL:
    raise ValueError("❌ BOT_TOKEN или RAILWAY_URL не заданы!")

# --- Создаём приложение Telegram ---
application = Application.builder().token(TOKEN).build()

# --- Хендлер /start ---
async def start(update: Update, context):
    await update.message.reply_text("✅ Привет! Бот запущен и готов к работе.")

# --- Хендлер на любые сообщения ---
async def echo(update: Update, context):
    await update.message.reply_text(f"Вы написали: {update.message.text}")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# --- FastAPI ---
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await application.initialize()
    webhook_url = f"{RAILWAY_URL}/webhook/{TOKEN}"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

@app.post(f"/webhook/{TOKEN}")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def root():
    return {"status": "бот запущен"}
