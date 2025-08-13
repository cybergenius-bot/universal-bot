import os
import asyncio
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ==== ENV ====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")              # токен бота от @BotFather
RAILWAY_URL    = os.getenv("RAILWAY_URL")                 # https://universal-bot-production.up.railway.app
WEBHOOK_PATH   = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL    = f"{RAILWAY_URL.rstrip('/')}{WEBHOOK_PATH}"

if not TELEGRAM_TOKEN or not RAILWAY_URL:
    raise RuntimeError("Нет TELEGRAM_TOKEN или RAILWAY_URL в переменных окружения")

# ==== Telegram Application ====
application: Application = Application.builder().token(TELEGRAM_TOKEN).build()

# Команды
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает. Пиши текст, пришли фото или голос.")

# Текст
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    await update.message.reply_text(f"Принял текст: «{text}». Базовый ответ — всё ок ✅")

# Фото
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📷 Фото получил. Анализ пока выключен — но событие ловится ✅")

# Голос
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎤 Голос получил. Распознавание подключим на следующем шаге ✅")

# Фоллбек
async def anything_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Я получил сообщение. Базовый хендлер сработал ✅")

# Регистрируем хендлеры
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
application.add_handler(MessageHandler(filters.VOICE, voice_handler))
application.add_handler(MessageHandler(filters.ALL, anything_handler))

# ==== FastAPI ====
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # ВАЖНО: корректная инициализация для webhook-режима
    await application.initialize()
    # Чистим старый вебхук и выставляем новый
    await application.bot.delete_webhook(drop_pending_updates=True)
    await application.bot.set_webhook(url=WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    # Корректно закрываем application
    await application.shutdown()
    await application.stop()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update = Update.de_json(data, application.bot)
    # Обрабатываем апдейт без запуска polling
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "ok", "webhook": WEBHOOK_URL}
