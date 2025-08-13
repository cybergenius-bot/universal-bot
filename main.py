import os
import io
import json
import asyncio
import logging
from typing import Optional

from fastapi import FastAPI
import uvicorn
import requests

from telegram import (
    Update, InputFile
)
from telegram.ext import (
    Application, ApplicationBuilder,
    CommandHandler, MessageHandler, ContextTypes, filters
)

# ============ ЛОГИ ============
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger("universal-bot")


# ============ ENV ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
RAILWAY_URL = os.getenv("RAILWAY_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "8080"))

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not OPENAI_API_KEY:
    log.warning("OPENAI_API_KEY is not set — ИИ-ответы работать не будут")
if not RAILWAY_URL:
    raise RuntimeError("RAILWAY_URL is not set (например: https://universal-bot-production.up.railway.app)")

# OpenAI HTTP endpoint (универсальный REST из их SDK 1.x)
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_TRANSCRIBE_URL = "https://api.openai.com/v1/audio/transcriptions"
OPENAI_VISION_MODEL = "gpt-4o-mini"
OPENAI_TEXT_MODEL = "gpt-4o-mini-translate"  # быстрый и дешёвый для текста


# ====== FASTAPI только для health ======
api = FastAPI()

@api.get("/health")
def health():
    return {"ok": True}


# ====== ВСПОМОГАТЕЛЬНОЕ: OpenAI ======
def openai_chat(messages, max_tokens: int = 500) -> str:
    """Простой вызов Chat Completion."""
    if not OPENAI_API_KEY:
        return "ИИ-движок не настроен."
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENAI_TEXT_MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens
    }
    resp = requests.post(OPENAI_CHAT_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def openai_vision_describe(image_url: str, prompt: str = "Опиши, что на изображении") -> str:
    """Вызов Vision: передаём URL телеграм-файла."""
    if not OPENAI_API_KEY:
        return "ИИ-движок не настроен."
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]}
    ]
    payload = {
        "model": OPENAI_VISION_MODEL,
        "messages": messages,
        "max_tokens": 500
    }
    resp = requests.post(OPENAI_CHAT_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def openai_transcribe_ogg(ogg_bytes: bytes) -> str:
    """Whisper-транскрипция голосового OGG/WEBM (телеграм voice)."""
    if not OPENAI_API_KEY:
        return "ИИ-движок не настроен."
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    files = {
        "file": ("audio.ogg", ogg_bytes, "audio/ogg"),
        "model": (None, "whisper-1")
    }
    resp = requests.post(OPENAI_TRANSCRIBE_URL, headers=headers, files=files, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data.get("text", "").strip() or "(пустая транскрипция)"


# ====== PAYPAL ======
def paypal_get_access_token() -> Optional[str]:
    if not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET):
        return None
    # По умолчанию — live. Для sandbox просто замени домен на api-m.sandbox.paypal.com
    base = os.getenv("PAYPAL_API_BASE", "https://api-m.paypal.com").rstrip("/")
    resp = requests.post(
        f"{base}/v1/oauth2/token",
        auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
        headers={"Accept": "application/json"},
        data={"grant_type": "client_credentials"},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json().get("access_token")


def paypal_create_order(amount: str = "3.00", currency: str = "USD") -> Optional[str]:
    """Создаёт заказ и возвращает ссылку на оплату (approve url)."""
    token = paypal_get_access_token()
    if not token:
        return None
    base = os.getenv("PAYPAL_API_BASE", "https://api-m.paypal.com").rstrip("/")
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {"currency_code": currency, "value": amount}
        }],
        "application_context": {
            "return_url": f"{RAILWAY_URL}/health",
            "cancel_url": f"{RAILWAY_URL}/health"
        }
    }
    resp = requests.post(
        f"{base}/v2/checkout/orders",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    approve = next((l["href"] for l in data["links"] if l["rel"] == "approve"), None)
    return approve


# ====== HANDLERS ======
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я универсальный бот 🤖\n\n"
        "Команды:\n"
        "• /help — помощь\n"
        "• /buy — ссылка на оплату PayPal\n\n"
        "Отправь текст, голос, фото или видео — отвечу."
    )
    await update.message.reply_text(text)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пиши вопросы, присылай голос/фото/видео.\n/paypal: /buy — получить ссылку на оплату.")


async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = paypal_create_order(amount="3.00", currency="USD")
    if not url:
        await update.message.reply_text("PayPal ещё не настроен. Проверь переменные PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET.")
        return
    await update.message.reply_text(f"Оплатить: {url}")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.message.text.strip()
    # Диалог к OpenAI
    ans = openai_chat([
        {"role": "system", "content": "Ты полезный ассистент. Отвечай кратко и по сути."},
        {"role": "user", "content": q}
    ], max_tokens=700)
    await update.message.reply_text(ans)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.message.voice or update.message.audio
    if not v:
        await update.message.reply_text("Не вижу голосовое сообщение.")
        return
    file = await context.bot.get_file(v.file_id)
    # Скачаем в память
    bio = io.BytesIO()
    await file.download_to_memory(out=bio)
    bio.seek(0)
    try:
        text = openai_transcribe_ogg(bio.read())
        # Затем ответим как на текст:
        ans = openai_chat([
            {"role": "system", "content": "Ты полезный ассистент. Отвечай кратко и по сути."},
            {"role": "user", "content": text}
        ], max_tokens=700)
        await update.message.reply_text(f"🗣 Распознано: {text}\n\nОтвет: {ans}")
    except Exception as e:
        log.exception("voice error")
        await update.message.reply_text("Не удалось распознать голос. Попробуй ещё раз.")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    # URL файла Телеграма подошёл для vision
    tg_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
    try:
        desc = openai_vision_describe(tg_url, "Опиши, что на фото, кратко и по пунктам.")
        await update.message.reply_text(desc)
    except Exception:
        log.exception("photo error")
        await update.message.reply_text("Не удалось описать фото.")


async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vid = update.message.video
    if not vid:
        await update.message.reply_text("Не вижу видео.")
        return
    file = await context.bot.get_file(vid.file_id)
    tg_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
    # Vision не «понимает» видео как видео — сделаем описание превью-кадра (thumbnail) если есть
    thumb_desc = "Видео получено. (Описание кадра: нет превью)"
    if vid.thumb:
        thumb = await context.bot.get_file(vid.thumb.file_id)
        thumb_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{thumb.file_path}"
        try:
            thumb_desc = openai_vision_describe(thumb_url, "Опиши превью-кадр видео.")
        except Exception:
            log.exception("video thumb describe error")
    await update.message.reply_text(f"Ссылка на файл: {tg_url}\n{thumb_desc}")


# ====== СБОРКА ПРИЛОЖЕНИЯ ======
async def post_init(app: Application):
    """Ставит вебхук при старте (важно для Railway)."""
    webhook_path = f"/{TELEGRAM_TOKEN}"
    full_url = f"{RAILWAY_URL}{webhook_path}"
    try:
        await app.bot.set_webhook(url=full_url, drop_pending_updates=True)
        log.info(f"Webhook set to {full_url}")
    except Exception:
        log.exception("Failed to set webhook")


def build_app() -> Application:
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )
    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("buy", cmd_buy))
    # Сообщения
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.VIDEO, on_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


async def run():
    # Запускаем Telegram веб-сервер (PTB) и FastAPI health параллельно.
    application = build_app()

    # PTB webhook server
    webhook_path = f"/{TELEGRAM_TOKEN}"
    webhook_runner = application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"{RAILWAY_URL}{webhook_path}",
        drop_pending_updates=True,
        stop_signals=None,   # управляем сами
        close_loop=False
    )

    # параллельно health на uvicorn (другой порт не нужен — тот же порт занят PTB)
    # Чтобы FastAPI был доступен, повесим его на тот же цикл событий как фон-задачу «без сервера»:
    # просто игнорируем — Railway видит активный порт из PTB.

    await webhook_runner


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except RuntimeError:
        # на некоторых платформах уже есть loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run())
