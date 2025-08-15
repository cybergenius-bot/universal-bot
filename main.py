import os
from fastapi import FastAPI, Request
from telegram.ext import Application, CommandHandler

# Получаем токен из переменных окружения
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в переменных окружения Railway!")

# Создаём Telegram Application
bot_app = Application.builder().token(TOKEN).build()

# Создаём FastAPI приложение
app = FastAPI()

# Хендлер команды /start
async def start(update, context):
    await update.message.reply_text("✅ Бот запущен и готов работать!")

bot_app.add_handler(CommandHandler("start", start))

# Роут для вебхука
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    await bot_app.update_queue.put(data)
    return {"ok": True}

# События старта и остановки приложения
@app.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    await bot_app.start()

@app.on_event("shutdown")
async def on_shutdown():
    await bot_app.stop()
    await bot_app.shutdown()
