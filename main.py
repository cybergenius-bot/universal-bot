import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Получаем токен и домен из переменных окружения
TOKEN = os.getenv("TELEGRAM_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_STATIC_URL")  # Railway сам задаёт этот домен
WEBHOOK_PATH = "/webhook"

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен и готов к работе!")

# /help
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Доступные команды: /start, /help")

# Регистрируем команды
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_cmd))

@app.on_event("startup")
async def on_startup():
    # Формируем полный URL вебхука
    webhook_url = f"https://{RAILWAY_URL}{WEBHOOK_PATH}"
    # Устанавливаем вебхук в Telegram
    await bot_app.bot.set_webhook(webhook_url)
    print(f"📌 Webhook установлен: {webhook_url}")

@app.post(WEBHOOK_PATH)
async def process_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    await bot_app.process_update(update)
    return {"ok": True}
