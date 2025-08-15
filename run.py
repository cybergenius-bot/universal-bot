import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI приложение
app = FastAPI()

# Переменные
TOKEN = os.getenv("TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_STATIC_URL")

if not TOKEN:
    raise ValueError("❌ Переменная TOKEN не установлена в Railway")

application = ApplicationBuilder().token(TOKEN).build()

# ====== Хэндлеры бота ======

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот запущен! Я вас слышу.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ Я готов отвечать на ваши вопросы!")

async def echo_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Вы сказали: {update.message.text}")

# Регистрируем команды
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_msg))

# ====== Запуск и остановка ======

@app.on_event("startup")
async def on_startup():
    webhook_url = f"https://{RAILWAY_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()

# ====== Обработка Telegram вебхука ======

@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# Проверка статуса сервера
@app.get("/")
async def root():
    return {"status": "ok", "message": "Bot is running"}
