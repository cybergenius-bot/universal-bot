import os
import logging
from fastapi import FastAPI, Request
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# -----------------------------
# Логирование
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -----------------------------
# Переменные окружения
# -----------------------------
TOKEN = os.getenv("TOKEN")  # Твой токен бота
BASE_URL = os.getenv("RAILWAY_STATIC_URL")  # Например: https://universal-bot-production.up.railway.app
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

# -----------------------------
# Инициализация FastAPI и Telegram Application
# -----------------------------
app = FastAPI()
application = ApplicationBuilder().token(TOKEN).build()

# -----------------------------
# Обработчики команд
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я работаю через Railway и Webhook 🚀")

application.add_handler(CommandHandler("start", start))

# -----------------------------
# Установка вебхука при старте
# -----------------------------
@app.on_event("startup")
async def on_startup():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            params={"url": WEBHOOK_URL}
        )
        logger.info(f"Webhook установлен: {WEBHOOK_URL}")
        logger.info(f"Результат установки: {resp.json()}")

# -----------------------------
# Удаление вебхука при остановке
# -----------------------------
@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()

# -----------------------------
# Приём апдейтов от Telegram
# -----------------------------
@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
