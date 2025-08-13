import os
import io
import base64
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

from openai import OpenAI

# ---------- настройки и клиенты ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("universal-bot")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # пример: https://universal-bot-production.up.railway.app/webhook

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is empty")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is empty")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is empty")

client = OpenAI(api_key=OPENAI_API_KEY)

# Telegram Application (PTB v20+)
application = Application.builder().token(TELEGRAM_TOKEN).build()

# FastAPI app
api = FastAPI(title="Universal Bot")

# ---------- обработчики ----------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот.\n"
        "📝 Напиши вопрос — отвечу.\n"
        "🎙️ Запиши голос — расшифрую и отвечу.\n"
        "🖼️ Пришли фото — опишу, что на нём."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text[:4000]

    reply = client.chat.completions.create(
        model="gpt-4o-mini",  # быстрый и недорогой
        messages=[
            {"role": "system", "content": "Ты helpful ассистент. Отвечай кратко и по делу."},
            {"role": "user", "content": user_text}
        ],
        temperature=0.6,
    )
    answer = reply.choices[0].message.content.strip()
    await update.message.reply_text(answer)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # скачиваем OGG/OPUS
    voice = update.message.voice
    tg_file = await context.bot.get_file(voice.file_id)
    bio = io.BytesIO()
    await tg_file.download_to_memory(out=bio)
    bio.seek(0)

    # транскрипция (Whisper)
    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=("voice.ogg", bio, "audio/ogg")
    )
    text = transcript.text.strip()
    if not text:
        await update.message.reply_text("Не смог распознать голос 😕")
        return

    # ответ на распознанный текст
    reply = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты helpful ассистент. Отвечай кратко и по делу."},
            {"role": "user", "content": text}
        ],
        temperature=0.6,
    )
    answer = reply.choices[0].message.content.strip()
    await update.message.reply_text(f"🗣️ Распознал: {text}\n\n💬 Ответ: {answer}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # берём самую большую версию фото
    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    bio = io.BytesIO()
    await tg_file.download_to_memory(out=bio)
    bio.seek(0)
    b64 = base64.b64encode(bio.read()).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64}"

    # визуальный анализ через multimodal
    reply = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты описываешь изображения кратко и информативно."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Опиши это фото и добавь полезные детали."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        temperature=0.4,
    )
    caption = reply.choices[0].message.content.strip()
    await update.message.reply_text(caption or "Не смог ничего описать 😕")

async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.exception("Unhandled error: %s", context.error)

# регистрируем хендлеры
application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_error_handler(handle_error)

# ---------- вебхук и lifecycle ----------

@api.get("/")
async def root():
    return {"ok": True, "service": "universal-bot"}

@api.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})

@api.on_event("startup")
async def _on_startup():
    # ВАЖНО: корректно запустить PTB перед установкой вебхука
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(WEBHOOK_URL)
    log.info("Webhook set to %s", WEBHOOK_URL)

@api.on_event("shutdown")
async def _on_shutdown():
    # Снять вебхук и корректно остановить PTB
    try:
        await application.bot.delete_webhook()
    except Exception:
        pass
    await application.stop()
    await application.shutdown()
    log.info("Bot stopped gracefully")
