import os
from fastapi import FastAPI, Request
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# Токен из переменной окружения
TOKEN = os.getenv("BOT_TOKEN")

# Создаём FastAPI приложение
app = FastAPI()

# Создаём Telegram Application
application = Application.builder().token(TOKEN).build()


# ===== Команды бота =====
async def start(update, context):
    await update.message.reply_text("Привет! Бот запущен и работает 24/7 🚀")


async def echo(update, context):
    await update.message.reply_text(f"Вы написали: {update.message.text}")


# Регистрируем обработчики
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))


# ===== Вебхук =====
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    await application.update_queue.put(data)
    return {"ok": True}
