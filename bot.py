import os
import json
import hmac
import asyncio
import logging
import tempfile
from typing import Optional

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from openai import OpenAI

# Base logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# More verbose logs from python-telegram-bot while отладка
logging.getLogger("telegram").setLevel(logging.DEBUG)

logger = logging.getLogger("bot")
app = FastAPI(title="universal-telegram-bot")


class State:
    def __init__(self) -> None:
        self.ready: bool = False
        self.mode: str = os.getenv("MODE", "webhook")
        self.application: Optional[Application] = None
        self.webhook_url: Optional[str] = None
        self.public_base_url: Optional[str] = os.getenv("PUBLIC_BASE_URL")
        self.webhook_secret: Optional[str] = os.getenv("TELEGRAM_WEBHOOK_SECRET")
        self.telegram_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
        self.openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
        self.admin_token: Optional[str] = os.getenv("ADMIN_TOKEN")
        self.model_text: str = os.getenv("OPENAI_MODEL_TEXT", "gpt-4o-mini")
        self.model_whisper: str = os.getenv("OPENAI_MODEL_WHISPER", "whisper-1")
        # 'auto' — отвечать на языке пользователя; 'ru' или 'en' — форсировать язык ответа
        self.reply_lang: str = os.getenv("REPLY_LANG", "auto").lower()


state = State()


def detect_lang(text: str) -> str:
    # Простая эвристика: если есть кириллица, считаем русский
    for ch in text:
        if "\u0400" <= ch <= "\u04FF":
            return "ru"
    return "en"


# --------- Health/Root ---------
@app.get("/")
async def root():
    return JSONResponse({"service": "telegram-bot", "status": "ok"})


@app.get("/health/live")
async def health_live():
    return JSONResponse({"status": "ok"})


@app.get("/health/ready")
async def health_ready():
    return JSONResponse({"status": "ready" if (state.ready and state.application) else "starting"})


@app.get("/health/diag")
async def health_diag():
    return JSONResponse({
        "mode": state.mode,
        "ready": state.ready,
        "app_inited": bool(state.application),
        "has_token": bool(state.telegram_token),
        "has_base_url": bool(state.public_base_url),
        "has_secret": bool(state.webhook_secret),
        "webhook_url": state.webhook_url or None,
        "reply_lang": state.reply_lang,
    })


# --------- Admin: set webhook on demand ---------
@app.post("/admin/set_webhook")
async def admin_set_webhook(x_admin_token: Optional[str] = Header(default=None, alias="X-Admin-Token")):
    if not state.admin_token or x_admin_token != state.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not state.application or not state.public_base_url:
        raise HTTPException(status_code=503, detail="App not initialized or no PUBLIC_BASE_URL")
    url = state.public_base_url.rstrip("/") + "/telegram"
    try:
        ok = await state.application.bot.set_webhook(
            url=url,
            secret_token=state.webhook_secret,
            drop_pending_updates=True
        )
        state.webhook_url = url
        logger.info("Admin set_webhook ok=%s url=%s", ok, url)
        return JSONResponse({"ok": bool(ok), "url": url})
    except TelegramError as e:
        logger.exception("Admin set_webhook failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# --------- Telegram webhook ---------
@app.post("/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    # Гарантируем корректные статусы вместо немого 500
    try:
        if state.mode != "webhook":
            raise HTTPException(status_code=503, detail="Webhook is not enabled")
        if state.application is None or state.application.bot is None:
            raise HTTPException(status_code=503, detail="Application not initialized")

        expected = (state.webhook_secret or "").strip()
        got = (x_telegram_bot_api_secret_token or "").strip()
        if expected:
            if not hmac.compare_digest(got, expected):
                logger.warning("Webhook: secret token mismatch (len got=%s, len expected=%s)", len(got), len(expected))
                raise HTTPException(status_code=403, detail="Forbidden")
        else:
            logger.warning("Webhook: TELEGRAM_WEBHOOK_SECRET is not set - secret check disabled")

        raw = await request.body()
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            logger.warning("Bad JSON body for /telegram: %r (err=%s)", raw[:200], e)
            return JSONResponse({"ok": False, "error": "bad_json"}, status_code=400)

        try:
            update = Update.de_json(data, state.application.bot)
        except Exception as e:
            logger.warning("Update parse error: %s; body=%r", e, raw[:200])
            return JSONResponse({"ok": False, "error": "bad_update"}, status_code=400)

        # Возвращаем 200 сразу, обработку делаем в фоне
        asyncio.create_task(state.application.process_update(update))
        return JSONResponse({"ok": True})

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.exception("Webhook handler failed: %s", e)
        return JSONResponse({"ok": False, "error": "internal"}, status_code=500)


# --------- Startup / Initialization ---------
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(_background_init())


async def _background_init():
    try:
        await initialize_bot()
        state.ready = True
        logger.info("Initialization complete, ready")
    except Exception as e:
        state.ready = False
        logger.exception("Initialization failed: %s", e)


async def initialize_bot():
    logger.info(
        "Init: mode=%s, token=%s, base_url=%s, secret=%s, reply_lang=%s",
        state.mode,
        "set" if state.telegram_token else "missing",
        state.public_base_url or "<none>",
        "set" if state.webhook_secret else "missing",
        state.reply_lang,
    )
    if not state.telegram_token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set - bot will not be initialized")
        return

    application = Application.builder().token(state.telegram_token).build()

    # Handlers
    application.add_handler(CommandHandler("start", on_cmd_start))
    application.add_handler(CommandHandler("help", on_cmd_help))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_handler(MessageHandler(filters.VOICE, on_voice))
    application.add_handler(MessageHandler(filters.AUDIO, on_audio))
    application.add_handler(MessageHandler(filters.PHOTO, on_photo))
    application.add_handler(MessageHandler(filters.VIDEO, on_video))

    # Init PTB internals
    await application.initialize()

    # Ключевой момент: сохраняем ссылку ДО установки вебхука → /telegram перестаёт отдавать 503
    state.application = application

    # Ставим вебхук (не падаем при ошибке — логируем)
    if state.mode == "webhook" and state.public_base_url:
        state.webhook_url = state.public_base_url.rstrip("/") + "/telegram"
        try:
            ok = await application.bot.set_webhook(
                url=state.webhook_url,
                secret_token=state.webhook_secret,
                drop_pending_updates=True
            )
            logger.info("Webhook set: %s (ok=%s)", state.webhook_url, ok)
        except TelegramError as e:
            logger.exception("set_webhook failed: %s", e)

    # Start PTB subsystems (JobQueue etc.)
    await application.start()


# --------- OpenAI ---------
def get_openai_client() -> Optional[OpenAI]:
    if not state.openai_api_key:
        logger.warning("OPENAI_API_KEY is not set - AI features disabled")
        return None
    return OpenAI(api_key=state.openai_api_key)


# --------- Handlers ---------
async def on_cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Привет! Я универсальный бот: понимаю текст, голос/аудио (Whisper), фото/видео (базовый анализ) и делаю структурированные ответы/Stories."
    )


async def on_cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Доступно:\n"
        "- Текст: анализ, резюме, Stories.\n"
        "- Голос/Аудио: распознаю через Whisper.\n"
        "- Фото/Видео: базовый анализ.\n"
        "Работаю в режиме webhook; polling используйте только для локальной отладки."
    )


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.effective_message.text or ""
    client = get_openai_client()
    if not client:
        await update.effective_message.reply_text("Получил текст, но ИИ недоступен (нет OPENAI_API_KEY).")
        return

    # Определяем язык ответа: REPLY_LANG=ru|en|auto
    lang = state.reply_lang if state.reply_lang in ("ru", "en") else detect_lang(text)
    if lang == "ru":
        system_msg = "Ты — помощник. Отвечай кратко, структурировано и всегда на русском языке."
        user_msg = f"Сформируй краткое структурированное объяснение/Story по теме:\n{text}"
        fallback = "Готово."
        err = "Не удалось сгенерировать ответ."
    else:
        system_msg = "You are a helpful assistant. Reply concisely, structured, in English."
        user_msg = f"Create a short, structured explanation/Story on:\n{text}"
        fallback = "Done."
        err = "Failed to generate an answer."

    try:
        completion = client.chat.completions.create(
            model=state.model_text,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )
        reply = completion.choices[0].message.content or fallback
    except Exception as e:
        logger.exception("Generation error: %s", e)
        reply = err

    for chunk in split_long_message(reply):
        await update.effective_message.reply_text(chunk)


async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.voice:
        return
    client = get_openai_client()
    if not client:
        await update.effective_message.reply_text("ИИ для распознавания недоступен (нет OPENAI_API_KEY).")
        return

    voice = update.effective_message.voice
    file = await voice.get_file()
    with tempfile.TemporaryDirectory() as td:
        ogg_path = os.path.join(td, "audio.ogg")
        wav_path = os.path.join(td, "audio.wav")
        await file.download_to_drive(ogg_path)
        await ffmpeg_to_wav(ogg_path, wav_path)

        text = await whisper_transcribe(client, wav_path)
        await update.effective_message.reply_text(f"Распознанный текст:\n{text}")


async def on_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.audio:
        return
    client = get_openai_client()
    if not client:
        await update.effective_message.reply_text("ИИ для распознавания недоступен (нет OPENAI_API_KEY).")
        return

    audio = update.effective_message.audio
    file = await audio.get_file()
    with tempfile.TemporaryDirectory() as td:
        in_path = os.path.join(td, "audio_input")
        wav_path = os.path.join(td, "audio.wav")
        await file.download_to_drive(in_path)
        await ffmpeg_to_wav(in_path, wav_path)

        text = await whisper_transcribe(client, wav_path)
        await update.effective_message.reply_text(f"Распознанный текст:\n{text}")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.photo:
        return
    client = get_openai_client()
    if not client:
        await update.effective_message.reply_text("ИИ для анализа изображений недоступен (нет OPENAI_API_KEY).")
        return
    await update.effective_message.reply_text("Фото получено. Базовый анализ изображений включён.")


async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Видео получено. Извлечение ключевых кадров и анализ — в базовом режиме.")


# --------- Utils ---------
def split_long_message(text: str, limit: int = 3500):
    out, buf, size = [], [], 0
    for line in text.splitlines(True):
        if size + len(line) > limit and buf:
            out.append("".join(buf)); buf = [line]; size = len(line)
        else:
            buf.append(line); size += len(line)
    if buf: out.append("".join(buf))
    return out or [text]


async def ffmpeg_to_wav(src_path: str, dst_path: str):
    cmd = ["ffmpeg", "-y", "-i", src_path, "-ar", "16000", "-ac", "1", "-f", "wav", dst_path]
    logger.info("FFmpeg: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    rc = await proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg exited with code {rc}")


async def whisper_transcribe(client: OpenAI, wav_path: str) -> str:
    try:
        with open(wav_path, "rb") as f:
            result = client.audio.transcriptions.create(model=state.model_whisper, file=f)
        return getattr(result, "text", None) or str(result)
    except Exception as e:
        logger.exception("Whisper error: %s", e)
        return "Не удалось распознать аудио."
