import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_PATH = "/webhook"
RAILWAY_URL = "universal-bot-production.up.railway.app"

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен и готов к работе!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Доступные команды: /start, /help")

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_cmd))

# --- Проверка сервера ---
@app.get("/")
async def root():
    return {"status": "ok"}

# --- Установка вебхука при старте ---
@app.on_event("startup")
async def on_startup():
    # Инициализируем PTB для работы в webhook-режиме
    await bot_app.initialize()
    webhook_url = f"https://{RAILWAY_URL}{WEBHOOK_PATH}"
    await bot_app.bot.set_webhook(webhook_url)
    print(f"📌 Webhook установлен: {webhook_url}")

# --- Обработка входящих апдейтов ---
@app.post(WEBHOOK_PATH)
async def process_webhook(request: Request):
    try:
        data = await request.json()
        print("📩 Пришло от Telegram:", data)
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        print("❌ Ошибка в обработке вебхука:", e)
        return {"ok": False, "error": str(e)}
