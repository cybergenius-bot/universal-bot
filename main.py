import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_PATH = "/webhook"
RAILWAY_URL = "universal-bot-production.up.railway.app"  # твой домен Railway

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# /start команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен и готов к работе!")

bot_app.add_handler(CommandHandler("start", start))

# Проверка, что сервер жив
@app.get("/")
async def root():
    return {"status": "ok"}

# Устанавливаем вебхук при старте
@app.on_event("startup")
async def on_startup():
    webhook_url = f"https://{RAILWAY_URL}{WEBHOOK_PATH}"
    await bot_app.bot.set_webhook(webhook_url)
    print(f"📌 Webhook установлен: {webhook_url}")

# Обрабатываем входящие запросы от Telegram
@app.post(WEBHOOK_PATH)
async def process_webhook(request: Request):
    data = await request.json()
    print("📩 Пришло от Telegram:", data)
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}
