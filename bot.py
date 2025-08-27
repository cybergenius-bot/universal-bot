# main.py
import os
import logging
from http import HTTPStatus
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager

# Важно: используем v20 API
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

application = (
    Application.builder()
    .token(TELEGRAM_TOKEN)
    .build()
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await application.bot.set_webhook(WEBHOOK_URL)
    async with application:
        yield

app = FastAPI(lifespan=lifespan)

@app.post("/")
async def deliver_update(request: Request):
    update_data = await request.json()
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)
    return Response(status_code=HTTPStatus.OK)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот на Webhook работает!")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, start))
