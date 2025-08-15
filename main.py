import os
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL", "")

if not TOKEN:
    raise ValueError("❌ Переменная BOT_TOKEN не задана!")

application = Application.builder().token(TOKEN).build()

app = FastAPI()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🚀 Начать", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Привет! Я готов к работе!", reply_markup=reply_markup)

application.add_handler(CommandHandler("start", start))

# Обработка вебхука
@app.post(f"/webhook/{TOKEN}")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

# Установка вебхука при старте
@app.on_event("startup")
async def on_startup():
    if RAILWAY_URL:
        await application.bot.set_webhook(f"{RAILWAY_URL}/webhook/{TOKEN}")
        print(f"✅ Webhook установлен: {RAILWAY_URL}/webhook/{TOKEN}")
    else:
        print("⚠ RAILWAY_URL не задан, вебхук не установлен!")

