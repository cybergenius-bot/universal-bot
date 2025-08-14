import os
import logging
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("universal-bot")

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
RAILWAY_URL = os.environ["RAILWAY_URL"].rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "123-ABC")

application = Application.builder().token(TELEGRAM_TOKEN).build()

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "Привет! Я на вебхуке. Пиши текст, присылай фото или голос — отвечу."
    )

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.effective_message.text or ""
    await update.effective_message.reply_text(f"Получил текст: «{txt}». Всё ок ✅")

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Фото пришло ✅")

async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Голосовое пришло ✅")

application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
application.add_handler(MessageHandler(filters.PHOTO, on_photo))
application.add_handler(MessageHandler(filters.VOICE, on_voice))

app = FastAPI(title="Universal Bot")

@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True}

@app.post(f"/webhook/{{secret}}")
async def handle_webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    await application.initialize()
    url = f"{RAILWAY_URL}/webhook/{WEBHOOK_SECRET}"
    # важный момент: сбросить старый вебхук и дропнуть хвост апдейтов
    await application.bot.delete_webhook(drop_pending_updates=True)
    ok = await application.bot.set_webhook(
        url=url,
        allowed_updates=["message","callback_query","my_chat_member","chat_member"]
    )
    log.info("Webhook set to %s -> %s", url, ok)

@app.on_event("shutdown")
async def on_shutdown():
    await application.shutdown()
    await application.stop()
    return {"ok": True}

# Инициализация PTB один раз (без polling!)
@app.on_event("startup")
async def on_startup():
    await tg.initialize()
