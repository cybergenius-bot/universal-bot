import os
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Лучше указывать из переменных

app = FastAPI()
bot = Bot(token=TOKEN)
application = Application.builder().token(TOKEN).build()

# Пример простого обработчика
async def handle_message(update: Update, context):
    logger.info(f"Received message from {update.effective_user.id}: {update.message.text}")
    await update.message.reply_text("Бот ответил!")

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook()
    await bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to {WEBHOOK_URL}")

@app.post("/telegram")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
        logger.info(f"Webhook payload: {data}")
        update = Update.de_json(data, bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        return Response(content='ok', status_code=200)
