import os
import io
import base64
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

from pydub import AudioSegment
from openai import OpenAI

# --------- ENV ----------
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
RAILWAY_URL   = os.environ["RAILWAY_URL"].rstrip("/")

# Модель для ответов (развёрнуто)
GPT_MODEL = "gpt-4o-mini"   # быстрая мультимодальная
MAX_TOKENS = 1600
TEMPERATURE = 0.8

client = OpenAI(api_key=OPENAI_API_KEY)

# --------- Telegram Application ----------
app_tg = Application.builder().token(TELEGRAM_TOKEN).build()

# /start
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Пиши текст, присылай фото, голосовые или видео — разберусь и отвечу развёрнуто."
    )

# Текст
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Развёрнутый ответ через Chat Completions
    resp = client.chat.completions.create(
        model=GPT_MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system",
             "content": "Отвечай развернуто, чётко по пунктам. Если просят инструкцию — дай пошагово. Язык пользователя сохраняй."},
            {"role": "user", "content": text}
        ],
    )
    answer = resp.choices[0].message.content.strip()
    await update.message.reply_text(answer)

# Фото (описание/анализ изображения, решение задач с фото)
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.photo:
        return
    # Берём максимальное качество
    file_id = msg.photo[-1].file_id
    tg_file = await context.bot.get_file(file_id)
    file_bytes = await tg_file.download_as_bytearray()

    # Кодируем в base64 для vision
    img_b64 = base64.b64encode(file_bytes).decode("utf-8")
    user_hint = (msg.caption or "").strip() or "Проанализируй изображение и ответь подробно."

    resp = client.chat.completions.create(
        model=GPT_MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system",
             "content": "Ты компьютерное зрение: поясняй подробно, если есть формулы — решай и расписывай шаги."},
            {"role": "user",
             "content": [
                 {"type": "text", "text": user_hint},
                 {"type": "image_url",
                  "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
             ]},
        ],
    )
    answer = resp.choices[0].message.content.strip()
    await msg.reply_text(answer)

# Голосовое → распознаём → даём развёрнутый ответ
async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    tg_file = await context.bot.get_file(voice.file_id)
    ogg_bytes = await tg_file.download_as_bytearray()

    # В wav для Whisper
    audio = AudioSegment.from_file(io.BytesIO(ogg_bytes), format="ogg")
    wav_buf = io.BytesIO()
    audio.export(wav_buf, format="wav")
    wav_buf.seek(0)

    # Распознаём
    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.wav", wav_buf, "audio/wav")
    )
    text = transcription.text.strip()

    # Отвечаем на распознанный текст
    resp = client.chat.completions.create(
        model=GPT_MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": "Отвечай развернуто, дружелюбно и по существу."},
            {"role": "user", "content": text},
        ],
    )
    answer = resp.choices[0].message.content.strip()
    await update.message.reply_text(f"Вы сказали: {text}\n\nОтвет:\n{answer}")

# Видео → берём аудио-дорожку → распознаём → отвечаем
async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    tg_file = await context.bot.get_file(video.file_id)
    mp4_bytes = await tg_file.download_as_bytearray()

    # Извлекаем аудио (через pydub требуется ffmpeg)
    video_audio = AudioSegment.from_file(io.BytesIO(mp4_bytes), format="mp4")
    wav_buf = io.BytesIO()
    video_audio.export(wav_buf, format="wav")
    wav_buf.seek(0)

    transcription = client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.wav", wav_buf, "audio/wav")
    )
    text = transcription.text.strip()

    resp = client.chat.completions.create(
        model=GPT_MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": "Отвечай подробно. Если просят конспект видео — дай тезисы и выводы."},
            {"role": "user", "content": text},
        ],
    )
    answer = resp.choices[0].message.content.strip()
    await update.message.reply_text(f"Из видео распознано: {text}\n\nОтвет:\n{answer}")

# Регистрируем хендлеры
app_tg.add_handler(CommandHandler("start", cmd_start))
app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
app_tg.add_handler(MessageHandler(filters.PHOTO, on_photo))
app_tg.add_handler(MessageHandler(filters.VOICE, on_voice))
app_tg.add_handler(MessageHandler(filters.VIDEO, on_video))

# --------- FastAPI + Webhook ----------
fastapi_app = FastAPI()

@fastapi_app.get("/")
async def health():
    return {"ok": True}

@fastapi_app.on_event("startup")
async def on_startup():
    # инициализируем PTB и ставим вебхук
    await app_tg.initialize()
    await app_tg.bot.set_webhook(f"{RAILWAY_URL}/webhook/{TELEGRAM_TOKEN}")

@fastapi_app.on_event("shutdown")
async def on_shutdown():
    await app_tg.shutdown()
    await app_tg.stop()

@fastapi_app.post(f"/webhook/{TELEGRAM_TOKEN}")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    update = Update.de_json(data, app_tg.bot)
    await app_tg.process_update(update)
    return {"ok": True}
