import os
import io
import asyncio
import logging
from typing import Optional

import requests
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder,
    CommandHandler, MessageHandler, ContextTypes, filters
)
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("universal-bot")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # пример: https://universal-bot-production.up.railway.app/webhook

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is not set")

# OpenAI client
oa = OpenAI(api_key=OPENAI_API_KEY)

# Telegram application
application: Application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# ---------- OpenAI helpers ----------

async def ask_ai(text: str) -> str:
    """Ответ ИИ на любой текстовый запрос."""
    try:
        resp = oa.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                 "content": "Ты универсальный помощник. Отвечай кратко, по делу, дружелюбно. Если просят инструкции — давай пошагово."},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.exception("OpenAI text error")
        return "Извини, сейчас не получилось ответить. Попробуй ещё раз."

def tg_file_url(file_path: str) -> str:
    return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

async def transcribe_voice(file_url: str) -> Optional[str]:
    """Распознаём речь из голосового/аудио (Whisper)."""
    try:
        data = requests.get(file_url, timeout=60).content
        file_like = io.BytesIO(data)
        file_like.name = "audio.ogg"
        tr = oa.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.ogg", file_like, "audio/ogg")
        )
        return tr.text.strip()
    except Exception:
        logger.exception("Whisper error")
        return None

async def describe_image(image_url: str, prompt: str = "Опиши изображение кратко:") -> str:
    """Подпись к фото через мультимодальную модель."""
    try:
        resp = oa.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты помогаешь описывать изображения."},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("Vision error")
        return "Не смог описать фото. Попробуй ещё раз."

# ---------- Telegram handlers ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот: текст, голос и фото. Спроси о чём угодно. 🎯"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    reply = await ask_ai(user_text)
    await update.message.reply_text(reply)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # voice и audio — оба случая
    tg_file = await (update.message.voice or update.message.audio).get_file()
    url = tg_file_url(tg_file.file_path)
    text = await transcribe_voice(url)
    if not text:
        await update.message.reply_text("Не смог распознать голос. Пришли ещё раз?")
        return
    ai = await ask_ai(f"Это распознавание речи пользователя: «{text}». Ответь по сути запроса.")
    await update.message.reply_text(ai)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Берём самую большую версию фото
    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    url = tg_file_url(tg_file.file_path)
    caption = update.message.caption or "Сделай краткую подпись и ключевые детали."
    desc = await describe_image(url, caption)
    await update.message.reply_text(desc)

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Видео пока не обрабатываю. Пришли голосовое (я распознаю речь) или фото. 🎙️🖼️"
    )

# Регистрируем обработчики (важно: НИЧЕГО не эхо-ответов)
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_handler(MessageHandler((filters.VOICE | filters.AUDIO), handle_voice))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, handle_video))

# ---------- FastAPI webhook ----------

api = FastAPI()

@api.on_event("startup")
async def _on_startup():
    # ставим вебхук
    await application.bot.set_webhook(url=WEBHOOK_URL)

@api.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# Локальный запуск (polling) — на Railway не используется
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(api, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
