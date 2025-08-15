import os
from fastapi import FastAPI, Request
from telegram.ext import Application, CommandHandler
import asyncio

# Читаем токен из переменных окружения Railway
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ Переменная BOT_TOKEN не задана! Проверь Railway → Settings → Variables")

# URL Railway, чтобы поставить вебхук
RAILWAY_URL = os.getenv("RAILWAY_URL")
if not RAILWAY_URL:
    raise ValueError("❌ Переменная RAILWAY_URL не задана! Пример: https://project-name.up.railway.app")

# Создаём FastAPI
app = FastAPI()

# Создаём Telegram Application
application = Application.builder().token(TOKEN).build()

# Обработчик /start
async def start(update, context):
    await update.message.reply_text("👋 Привет! Бот запущен и готов к работе ✅")

application.add_handler(CommandHandler("start", start))

# При старте приложения — ставим вебхук
@app.on_event("startup")
async def startup_event():
    await application.bot.set_webhook(f"{RAILWAY_URL}/webhook")
    print(f"✅ Webhook установлен: {RAILWAY_URL}/webhook")

# При остановке — останавливаем бота
@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()

# FastAPI маршрут для приёма обновлений
@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    await application.update_queue.put(update)
    return {"status": "ok"}
