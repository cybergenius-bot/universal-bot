import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("BOT_TOKEN")

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# Команда /start
async def start(update: Update, context):
    await update.message.reply_text("✅ Бот работает! Напиши что-нибудь.")

# Ответ на любое сообщение
async def echo(update: Update, context):
    await update.message.reply_text(f"Ты написал: {update.message.text}")

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"status": "ok"}

@app.on_event("startup")
async def startup_event():
    print("🚀 Бот запущен!")

