import os
import io
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# ==== ENV ====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # опционально
# PUBLIC_URL: можно задать вручную в переменных Railway.
# Если не указан, пробуем домен, который выставляет Railway.
PUBLIC_URL = (
    os.getenv("PUBLIC_URL")
    or (f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}" if os.getenv("RAILWAY_PUBLIC_DOMAIN") else None)
)

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")

# ==== OpenAI (опционально) ====
openai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        openai_client = None  # если библиотека не установлена — просто игнорируем

# ==== Telegram Application ====
application: Application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

# ===== Handlers =====

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Спроси о чем угодно.\n"
        "Могу понимать текст и голосовые сообщения."
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # Если есть ключ OpenAI — просим ИИ ответить «по‑умному»
    if openai_client:
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Отвечай кратко, понятно и по делу, на русском."},
                    {"role": "user", "content": text},
                ],
            )
            answer = resp.choices[0].message.content.strip()
            await update.message.reply_text(answer)
            return
        except Exception as e:
            # Если что-то пошло не так — не молчим
            await update.message.reply_text(f"Ответил бы умно, но возникла ошибка ИИ: {e}\nОтвечаю сам.")

    # Фолбэк — просто эхо с пометкой
    await update.message.reply_text(f"Ты написал: {text}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Скачиваем голосовое, отправляем в Whisper, отвечаем расшифровкой и ответом ИИ (если есть)."""
    try:
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)
        bio = io.BytesIO()
        await file.download_to_memory(out=bio)
        bio.seek(0)

        transcript_text = None
        if openai_client:
            try:
                tr = openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=("voice.ogg", bio, "audio/ogg")
                )
                transcript_text = tr.text.strip() if hasattr(tr, "text") else None
            except Exception as e:
                transcript_text = None
                await update.message.reply_text(f"Не удалось расшифровать голос: {e}")

        if transcript_text:
            # Если удалось расшифровать — отвечаем содержательно
            if openai_client:
                try:
                    resp = openai_client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[
                            {"role": "system", "content": "Отвечай кратко, понятно и по делу, на русском."},
                            {"role": "user", "content": transcript_text},
                        ],
                    )
                    answer = resp.choices[0].message.content.strip()
                    await update.message.reply_text(f"Вы сказали: {transcript_text}\n\nОтвет: {answer}")
                    return
                except Exception as e:
                    await update.message.reply_text(f"Ошибка при ответе ИИ: {e}\nВы сказали: {transcript_text}")
                    return
            # Если OpenAI нет — просто отдать расшифровку
            await update.message.reply_text(f"Вы сказали: {transcript_text}")
        else:
            await update.message.reply_text("Не смог распознать голос. Попробуй ещё раз.")
    except Exception as e:
        await update.message.reply_text(f"Не получилось обработать голосовое: {e}")

# Регистрируем обработчики
application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# ===== FastAPI + lifespan =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    await application.initialize()
    await application.start()

    # Ставим вебхук, если известен публичный URL
    if PUBLIC_URL:
        webhook_url = f"{PUBLIC_URL.rstrip('/')}/webhook/{TELEGRAM_TOKEN}"
        try:
            await application.bot.set_webhook(webhook_url, allowed_updates=["message"])
        except Exception:
            # если не удалось — оставим без вебхука (можно будет поставить вручную)
            pass

    yield  # здесь приложение работает

    # shutdown
    try:
        await application.bot.delete_webhook()
    except Exception:
        pass
    await application.stop()
    await application.shutdown()

api = FastAPI(title="Universal Bot", lifespan=lifespan)

@api.get("/")
async def root():
    return PlainTextResponse("OK")

@api.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        return JSONResponse({"ok": False, "error": "bad token"}, status_code=403)

    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})
    log.info("Bot stopped gracefully")
