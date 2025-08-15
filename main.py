import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")  # Токен из переменной окружения
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{os.getenv('RAILWAY_URL')}{WEBHOOK_PATH}"

app = FastAPI()

# Создаём приложение Telegram
telegram_app = Application.builder().token(TOKEN).build()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Бот запущен и готов к работе.")

telegram_app.add_handler(CommandHandler("start", start))

# Устанавливаем webhook при старте FastAPI
@app.on_event("startup")
async def on_startup():
    await telegram_app.bot.set_webhook(WEBHOOK_URL)

# Маршрут для Telegram webhook
@app.post(WEBHOOK_PATH)
async def webhook_handler(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"ok": True}
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
