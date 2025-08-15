import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
import asyncio

# Загружаем переменные окружения
TOKEN = os.getenv("BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")

if not TOKEN:
    raise ValueError("❌ Переменная BOT_TOKEN не задана!")
if not RAILWAY_URL:
    raise ValueError("❌ Переменная RAILWAY_URL не задана!")

# Создаём приложение Telegram
application = Application.builder().token(TOKEN).build()

# Команды бота
async def start(update: Update, context):
    await update.message.reply_text("✅ Привет! Бот запущен и готов к работе.")

async def echo(update: Update, context):
    await update.message.reply_text(update.message.text)

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Создаём FastAPI
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    await application.bot.set_webhook(f"{RAILWAY_URL}/webhook/{TOKEN}")
    print(f"✅ Webhook установлен: {RAILWAY_URL}/webhook/{TOKEN}")

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TOKEN:
        return {"status": "forbidden"}
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return {"status": "ok"}

@app.get("/")
async def home():
    return {"status": "бот работает"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
