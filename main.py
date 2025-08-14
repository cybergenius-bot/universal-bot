from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application

import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
RAILWAY_URL = os.getenv("RAILWAY_URL")

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

@app.post(f"/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}

@app.on_event("startup")
async def on_startup():
    await bot_app.bot.set_webhook(f"{RAILWAY_URL}/{WEBHOOK_SECRET}")

@bot_app.message_handler()
async def echo(update: Update, context):
    await update.message.reply_text("Бот работает! 🚀")
