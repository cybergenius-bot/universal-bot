import os
import base64
import io

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import os
import io
import base64
import asyncio
import subprocess
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from pydub import AudioSegment
from openai import OpenAI

# ---------- ENV ----------
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
PUBLIC_URL = os.environ.get("WEBHOOK_URL") or os.environ.get("RAILWAY_URL")

# ---------- CLIENTS ----------
client = OpenAI(api_key=OPENAI_API_KEY)
app = FastAPI()
application = Application.builder().token(TELEGRAM_TOKEN).build()

# ---------- STYLE (развёрнутые ответы) ----------
SYSTEM_PROMPT = (
    "Ты универсальный помощник. Отвечай подробно, структурированно и понятно: "
    "краткое резюме → шаги решения → детали/примеры. Если есть формулы, пиши их текстом."
)

# ---------- LLM HELPERS ----------
async def ask_llm_text(user_text: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text}
        ],
        max_tokens=800,
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

async def ask_llm_vision(question: str, image_bytes: bytes) -> str:
    content = [
        {"type": "text", "text": question or "Проанализируй изображение и ответь развёрнуто."},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_b64(image_bytes)}"}}
    ]
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content}
        ],
        max_tokens=800,
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()

# ---------- HANDLERS ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Пиши вопрос, или пришли фото/видео/голос — разберу и отвечу подробно."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    reply = await ask_llm_text(text)
    await update.message.reply_text(reply)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = update.message.photo[-1]
        tgfile = await context.bot.get_file(photo.file_id)
        bio = io.BytesIO()
        await tgfile.download_to_memory(out=bio)
        bio.seek(0)
        caption = update.message.caption or ""
        reply = await ask_llm_vision(caption, bio.read())
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Не удалось обработать фото: {e}")

def extract_frame_from_video(video_bytes: bytes) -> bytes:
    """Берём первый кадр из видео при помощи ffmpeg (нужен nixpacks.toml)."""
    proc = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-vf", "fps=1", "-vframes", "1",
         "-f", "image2pipe", "pipe:1"],
        input=video_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return proc.stdout

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tgfile = await context.bot.get_file(update.message.video.file_id)
        bio = io.BytesIO()
        await tgfile.download_to_memory(out=bio)
        frame = extract_frame_from_video(bio.getvalue())
        if not frame:
            await update.message.reply_text("Не удалось извлечь кадр из видео.")
            return
        caption = update.message.caption or ""
        reply = await ask_llm_vision(caption, frame)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(f"Не удалось обработать видео: {e}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачиваем .ogg (opus) → ffmpeg через pydub → WAV → Whisper → LLM."""
    try:
        tgfile = await context.bot.get_file(update.message.voice.file_id)
        ogg_mem = io.BytesIO()
        await tgfile.download_to_memory(out=ogg_mem)
        ogg_mem.seek(0)

        wav_mem = io.BytesIO()
        AudioSegment.from_file(ogg_mem, format="ogg").export(wav_mem, format="wav")
        wav_mem.seek(0)

        tr = client.audio.transcriptions.create(
            model="whisper-1",
            file=("speech.wav", wav_mem, "audio/wav"),
            response_format="text",
        )
        transcript = tr if isinstance(tr, str) else getattr(tr, "text", str(tr))
        reply = await ask_llm_text(f"Пользователь сказал: {transcript}")
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(
            "Не получилось распознать голос. Проверь, что сообщение не пустое и попробуй ещё раз.\n"
            f"Тех. подробности: {e}"
        )

# Регистрируем обработчики
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))
application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
application.add_handler(MessageHandler(filters.VIDEO, handle_video))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ---------- FASTAPI + WEBHOOK ----------
@app.on_event("startup")
async def _on_startup():
    if not PUBLIC_URL:
        print("WARNING: PUBLIC_URL (WEBHOOK_URL/RAILWAY_URL) не задан — webhook не поставится.")
        return
    await application.initialize()
    await application.bot.set_webhook(f"{PUBLIC_URL}/webhook")
    await application.start()
    print("Webhook set:", f"{PUBLIC_URL}/webhook")

@app.on_event("shutdown")
async def _on_shutdown():
    await application.stop()
    await application.shutdown()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

@app.get("/")
def health():
    return {"ok": True}
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    update = Update.de_json(data, app_tg.bot)
    await app_tg.process_update(update)
    return {"ok": True}
