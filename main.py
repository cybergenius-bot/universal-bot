import os
from fastapi import FastAPI, Request
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Загружаем переменные окружения
TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")

if not TOKEN:
    raise ValueError("❌ Переменная BOT_TOKEN не задана!")

if not RAILWAY_URL:
    print("⚠️ ВНИМАНИЕ: Переменная RAILWAY_URL не задана! Webhook не будет установлен.")

# Создаём приложение Telegram
application = Application.builder().token(TOKEN).build()

# Команда /start
async def start(update, context):
    await update.message.reply_text("👋 Привет! Бот запущен и готов к работе!")

# Ответ на любое сообщение
async def echo(update, context):
    await update.message.reply_text(f"Вы написали: {update.message.text}")

# Регистрируем команды и обработчики
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# FastAPI сервер
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    if RAILWAY_URL:
        await application.bot.set_webhook(f"{RAILWAY_URL}/webhook")
        print(f"✅ Webhook установлен: {RAILWAY_URL}/webhook")
    else:
        print("⚠️ Webhook не установлен — нет RAILWAY_URL")

@app.post("/webhook")
async def webhook_endpoint(request: Request):
    data = await request.json()
    await application.update_queue.put(data)
    return {"status": "ok"}
