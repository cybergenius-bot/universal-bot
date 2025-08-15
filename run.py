import os
import logging
from fastapi import FastAPI, Request
from telegram.ext import ApplicationBuilder, CommandHandler

# Логи, чтобы видеть что происходит
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Читаем токен из переменных окружения Railway
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в переменных окружения Railway!")

# Создаём приложение Telegram
application = ApplicationBuilder().token(TOKEN).build()

# Простой тест-командой
async def start(update, context):
    await update.message.reply_text("✅ Бот запущен и работает!")

application.add_handler(CommandHandler("start", start))

# FastAPI сервер
app = FastAPI()

@app.on_event("startup")
async def startup_event():
    webhook_url = f"https://universal-bot-production.up.railway.app/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")

@app.post("/webhook")
async def webhook_handler(request: Request):
    data = await request.json()
    await application.update_queue.put(data)
    return {"ok": True}

# Главная страница (для проверки)
@app.get("/")
async def root():
    return {"status": "ok", "message": "Бот работает через Webhook"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("run:app", host="0.0.0.0", port=port)
