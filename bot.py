from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import Application, Dispatcher, MessageHandler, filters
import os
import asyncio

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = "https://universal-bot-production.up.railway.app/telegram"

app = FastAPI()
bot = Bot(TOKEN)
application = Application.builder().token(TOKEN).build()


@app.on_event("startup")
async def startup():
    await bot.delete_webhook()
    await bot.set_webhook(url=WEBHOOK_URL)


@app.post("/telegram")
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, bot)
    await application.process_update(update)
    return {"ok": True}


# Пример хендлера
async def handle_message(update: Update, context):
    await update.message.reply_text("Привет! Я работаю на Webhook.")

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
