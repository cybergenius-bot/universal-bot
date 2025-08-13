import os
import io
import base64
import asyncio
import subprocess
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

from pydub import AudioSegment  # для совместимости, но конвертим через ffmpeg
from PIL import Image

from openai import OpenAI

# --------- ENV / глобалы ---------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAILWAY_URL = os.getenv("RAILWAY_URL")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")
if not RAILWAY_URL:
    raise RuntimeError("RAILWAY_URL is not set (пример: https://<service>.up.railway.app)")

client = OpenAI(api_key=OPENAI_API_KEY)

# Модели
LLM_VISION_MODEL = "gpt-4o-mini"   # умеет видеть картинки
LLM_TEXT_MODEL   = "gpt-4o-mini"   # для обычного текста (можно одну и ту же)
ASR_MODEL        = "whisper-1"     # распознавание речи

# Telegram application (одно на весь процесс)
application: Application = Application.builder().token(TELEGRAM_TOKEN).build()

# FastAPI app
app = FastAPI(title="Universal Bot")

# --------- Утилиты ---------
def run_ffmpeg(input_path: str, output_path: str, args: list[str]) -> None:
    """
    Запускает ffmpeg. Бросает CalledProcessError при ошибке.
    """
    cmd = ["ffmpeg", "-y", "-i", input_path, *args, output_path]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

def b64_image_from_bytes(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("utf-8")


# --------- Хэндлеры Telegram ---------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я универсальный бот.\n"
        "Я понимаю текст, фото, видео и голосовые. Просто отправь сообщение.\n"
        "Старайся задавать вопросы конкретно — я отвечаю развёрнуто."
    )
    await update.message.reply_text(text)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    try:
        system_prompt = (
            "Ты универсальный помощник. Отвечай развёрнуто, по шагам, "
            "с пояснениями и примерами, структурируй ответ списками."
        )
        cmpl = client.chat.completions.create(
            model=LLM_TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.6,
            max_tokens=900,
        )
        answer = cmpl.choices[0].message.content.strip()
        await update.message.reply_text(answer)
    except Exception as e:
        await update.message.reply_text("Не удалось сгенерировать ответ.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    photo = update.message.photo[-1]
    tg_file = await context.bot.get_file(photo.file_id)
    img_bytes = await tg_file.download_as_bytearray()
    img_b64 = b64_image_from_bytes(bytes(img_bytes))

    prompt = (
        "Проанализируй изображение. Опиши подробно, структурировано. "
        "Если видишь текст/формулы/задачу — реши по шагам и объясни."
    )
    try:
        cmpl = client.chat.completions.create(
            model=LLM_VISION_MODEL,
            messages=[
                {"role": "system", "content": "Ты эксперт по анализу изображений."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": img_b64}},
                    ],
                },
            ],
            temperature=0.4,
            max_tokens=1000,
        )
        answer = cmpl.choices[0].message.content.strip()
        await update.message.reply_text(answer)
    except Exception:
        await update.message.reply_text("Не удалось проанализировать фото.")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.video:
        return

    tg_file = await context.bot.get_file(update.message.video.file_id)
    mp4_path = "/tmp/in.mp4"
    jpg_path = "/tmp/frame.jpg"
    with open(mp4_path, "wb") as f:
        f.write(await tg_file.download_as_bytearray())

    try:
        # Берём кадр на 1-й секунде
        run_ffmpeg(mp4_path, jpg_path, ["-ss", "00:00:01", "-frames:v", "1"])
        with open(jpg_path, "rb") as f:
            frame_bytes = f.read()
        img_b64 = b64_image_from_bytes(frame_bytes)
    except Exception:
        await update.message.reply_text("Не удалось обработать видео.")
        return

    prompt = (
        "Проанализируй кадр из видео: что происходит, какие важные объекты. "
        "Если виден текст/формулы — объясни и реши по шагам."
    )
    try:
        cmpl = client.chat.completions.create(
            model=LLM_VISION_MODEL,
            messages=[
                {"role": "system", "content": "Ты эксперт по анализу изображений/кадров видео."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": img_b64}},
                    ],
                },
            ],
            temperature=0.4,
            max_tokens=1000,
        )
        answer = cmpl.choices[0].message.content.strip()
        await update.message.reply_text(answer)
    except Exception:
        await update.message.reply_text("Не удалось проанализировать видео.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.voice:
        return

    tg_file = await context.bot.get_file(update.message.voice.file_id)
    ogg_path = "/tmp/in.ogg"
    wav_path = "/tmp/out.wav"
    with open(ogg_path, "wb") as f:
        f.write(await tg_file.download_as_bytearray())

    # Конвертируем OGG/Opus -> WAV (16kHz, mono). Нужен ffmpeg в системе.
    try:
        run_ffmpeg(ogg_path, wav_path, ["-ar", "16000", "-ac", "1"])
    except subprocess.CalledProcessError:
        await update.message.reply_text("Не удалось обработать голос (ffmpeg).")
        return

    # Распознаём речь
    try:
        with open(wav_path, "rb") as f:
            tr = client.audio.transcriptions.create(model=ASR_MODEL, file=f)
        user_text = tr.text.strip()
    except Exception:
        await update.message.reply_text("Не удалось распознать голос.")
        return

    # Отвечаем развёрнуто
    try:
        system_prompt = (
            "Ты универсальный помощник. Ответ дай развёрнуто и по шагам, "
            "если нужен расчёт — покажи ход решения."
        )
        cmpl = client.chat.completions.create(
            model=LLM_TEXT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.6,
            max_tokens=900,
        )
        answer = cmpl.choices[0].message.content.strip()
        await update.message.reply_text(answer)
    except Exception:
        await update.message.reply_text("Ошибка генерации ответа.")


# Регистрируем хэндлеры
application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.VIDEO, handle_video))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


# --------- FastAPI lifecycle / webhook ---------
@app.on_event("startup")
async def on_startup():
    # ВАЖНО: корректная инициализация PTB (иначе будут ошибки event loop)
    await application.initialize()
    # Запуск внутренних фоновых задач PTB (очередь апдейтов и т.п.)
    await application.start()

    # Ставим вебхук на наш публичный URL
    webhook_url = f"{RAILWAY_URL}/{TELEGRAM_TOKEN}"
    await application.bot.set_webhook(webhook_url)

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await application.bot.delete_webhook()
    except Exception:
        pass
    await application.stop()
    await application.shutdown()


@app.get("/", response_class=PlainTextResponse)
async def root():
    return "OK"

@app.post("/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    update = Update.de_json(data=data, bot=application.bot)
    # Обрабатываем апдейт напрямую (без дополнительного веб-сервера PTB)
    await application.process_update(update)
    return {"ok": True}
