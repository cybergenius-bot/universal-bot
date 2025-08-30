import os
import io
import asyncio
import logging
import subprocess
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------- Логирование ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(message)s]"
)
logger = logging.getLogger("bot")

# ---------- Конфигурация из окружения ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")  # напр. https://your-app.up.railway.app

WEBHOOK_PATH = "/telegram"
WEBHOOK_URL = f"{PUBLIC_BASE_URL}{WEBHOOK_PATH}" if PUBLIC_BASE_URL else ""

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ---------- OpenAI клиент (Whisper) ----------
try:
    from openai import OpenAI
    openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
    logger.warning("OpenAI SDK не инициализирован: %s", e)
    openai_client = None

# ---------- Глобальная ссылка на PTB Application ----------
application: Optional[Application] = None


# ---------- Утилиты для загрузки и конвертации аудио ----------
class NamedBytesIO(io.BytesIO):
    def __init__(self, data: bytes, name: str):
        super().__init__(data)
        self.name = name

async def tg_download_bytes(bot, file_id: str) -> bytes:
    tg_file = await bot.get_file(file_id)
    bio = io.BytesIO()
    await tg_file.download_to_memory(out=bio)
    return bio.getvalue()

def ffmpeg_bytes_to_wav_sync(src_bytes: bytes, input_codec_hint: Optional[str] = None) -> bytes:
    """
    Универсальная конвертация в WAV 16kHz mono через ffmpeg (CPU).
    input_codec_hint не обязателен. Выполняется синхронно, вызывать через asyncio.to_thread().
    """
    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-y",
        "-i", "pipe:0",
        "-vn",             # без видео
        "-ac", "1",        # mono
        "-ar", "16000",    # 16kHz
        "-f", "wav",
        "pipe:1",
    ]
    proc = subprocess.run(
        cmd,
        input=src_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return proc.stdout

def whisper_transcribe_sync(data: bytes, name: str, language: Optional[str] = "ru") -> str:
    """
    Синхронный вызов OpenAI Whisper. Вернёт чистый текст (response_format='text').
    """
    if not openai_client:
        raise RuntimeError("OPENAI_API_KEY не установлен или OpenAI клиент не инициализирован.")
    audio_file = NamedBytesIO(data, name)
    # Возвращает str при response_format="text"
    text = openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
        response_format="text",
        language=language or "ru",
        temperature=0,
    )
    return text  # type: ignore[return-value]


# ---------- Хендлеры команд ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Привет! 👋 Я универсальный ИИ‑бот.\n"
        "Бесплатно: 5 запросов. Тарифы: /pricing. Покупка: /buy\n"
        "Реферальная ссылка: /ref\n"
        "Пришлите текст/голос/фото/видео."
    )
    await update.message.reply_text(text)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Справка: пришлите текст/голос/фото/видео — отвечу. Команды: /pricing /buy /ref /status")

async def cmd_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Тарифы: Free 5 Q, $10 → 20 Q, $30 → 200 Q, $50 → безлимит/мес.")

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Покупка скоро. В данный момент доступен PayPal (в разработке) и Telegram Stars (запланировано).")

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    me = await context.bot.get_me()
    user = update.effective_user
    ref_param = f"ref{user.id}" if user else "ref0"
    await update.message.reply_text(f"Ваша реф. ссылка: https://t.me/{me.username}?start={ref_param}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Статус: онлайн ✅")


# ---------- Хендлеры текста и мультимедиа ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user_text = update.message.text.strip()
    # Здесь может быть GPT‑4o ответ; для надёжности — эхо-ответ
    await update.message.reply_text(f"Вы написали: {user_text}")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.voice:
        return
    try:
        ogg_bytes = await tg_download_bytes(context.bot, update.message.voice.file_id)

        # Попытка 1: прямо отдать OGG в Whisper
        try:
            text = await asyncio.to_thread(whisper_transcribe_sync, ogg_bytes, "audio.ogg", "ru")
        except Exception as e1:
            logger.warning("OGG→Whisper не прошёл, пробуем ffmpeg→WAV: %s", e1)
            wav_bytes = await asyncio.to_thread(ffmpeg_bytes_to_wav_sync, ogg_bytes)
            text = await asyncio.to_thread(whisper_transcribe_sync, wav_bytes, "audio.wav", "ru")

        text = (text or "").strip()
        if not text:
            await update.message.reply_text("Не удалось распознать голосовое сообщение. Попробуйте ещё раз.")
            return

        # Здесь можно подставить ваш GPT‑пайплайн. Пока — ответим распознанным текстом:
        await update.message.reply_text(text)

    except Exception as e:
        logger.exception("Voice STT failed: %s", e)
        await update.message.reply_text("Не удалось распознать голос. Попробуйте ещё раз или пришлите текст.")

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.audio:
        return
    try:
        file_bytes = await tg_download_bytes(context.bot, update.message.audio.file_id)
        # Прямая попытка (mp3/m4a/wav часто проходят)
        try:
            name = (update.message.audio.file_name or "audio").lower()
            text = await asyncio.to_thread(whisper_transcribe_sync, file_bytes, name, "ru")
        except Exception:
            wav_bytes = await asyncio.to_thread(ffmpeg_bytes_to_wav_sync, file_bytes)
            text = await asyncio.to_thread(whisper_transcribe_sync, wav_bytes, "audio.wav", "ru")
        text = (text or "").strip()
        if not text:
            await update.message.reply_text("Не удалось распознать аудио.")
            return
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("Audio STT failed: %s", e)
        await update.message.reply_text("Не удалось распознать аудио. Попробуйте ещё раз или пришлите текст.")

async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.video_note:
        return
    try:
        mp4_bytes = await tg_download_bytes(context.bot, update.message.video_note.file_id)

        def mp4_to_wav_sync(src: bytes) -> bytes:
            proc = subprocess.run(
                [
                    "ffmpeg", "-loglevel", "error", "-y",
                    "-i", "pipe:0",
                    "-vn", "-ac", "1", "-ar", "16000",
                    "-f", "wav", "pipe:1",
                ],
                input=src,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return proc.stdout

        wav_bytes = await asyncio.to_thread(mp4_to_wav_sync, mp4_bytes)
        text = await asyncio.to_thread(whisper_transcribe_sync, wav_bytes, "audio.wav", "ru")
        text = (text or "").strip()
        if not text:
            await update.message.reply_text("Не удалось распознать видеокружок.")
            return
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("VideoNote STT failed: %s", e)
        await update.message.reply_text("Не удалось распознать видеокружок. Попробуйте ещё раз.")


def register_handlers(app_ptb: Application) -> None:
    # Команды
    app_ptb.add_handler(CommandHandler("start", cmd_start))
    app_ptb.add_handler(CommandHandler("help", cmd_help))
    app_ptb.add_handler(CommandHandler("pricing", cmd_pricing))
    app_ptb.add_handler(CommandHandler("buy", cmd_buy))
    app_ptb.add_handler(CommandHandler("ref", cmd_ref))
    app_ptb.add_handler(CommandHandler("status", cmd_status))
    # Медиа
    app_ptb.add_handler(MessageHandler(filters.VOICE, handle_voice), group=0)
    app_ptb.add_handler(MessageHandler(filters.AUDIO, handle_audio), group=0)
    app_ptb.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note), group=0)
    # Текст
    app_ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text), group=1)


def create_ptb_application() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена.")
    app_ptb = Application.builder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
    register_handlers(app_ptb)
    return app_ptb


# ---------- FastAPI + lifespan ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global application
    try:
        application = create_ptb_application()
        await application.initialize()
        await application.start()

        # Настройка вебхука (если задан PUBLIC_BASE_URL и секрет)
        if WEBHOOK_URL and TELEGRAM_WEBHOOK_SECRET:
            try:
                await application.bot.delete_webhook(drop_pending_updates=True)
            except Exception as e:
                logger.warning("Не удалось удалить вебхук перед установкой: %s", e)

            await application.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=TELEGRAM_WEBHOOK_SECRET,
                drop_pending_updates=True,
                allowed_updates=[
                    "message", "edited_message", "callback_query", "chat_member",
                    "pre_checkout_query", "channel_post", "edited_channel_post",
                    "shipping_query",
                ],
            )
            logger.info("✅ Webhook установлен: %s", WEBHOOK_URL)
        else:
            logger.warning("PUBLIC_BASE_URL или TELEGRAM_WEBHOOK_SECRET не заданы — вебхук НЕ установлен автоматически.")

        yield
    except Exception as e:
        logger.error("❌ Ошибка при запуске приложения: %s", e, exc_info=True)
        raise
    finally:
        try:
            if application:
                try:
                    await application.bot.delete_webhook(drop_pending_updates=False)
                    logger.info("✅ Webhook удалён при остановке")
                except Exception as e:
                    logger.warning("Не удалось удалить вебхук при остановке: %s", e)

                await application.stop()
                await application.shutdown()
        except Exception as e:
            logger.error("❌ Ошибка при остановке: %s", e, exc_info=True)


app = FastAPI(
    title="Telegram Bot",
    description="Телеграм бот на FastAPI + PTB",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/")
async def root():
    return {"message": "Telegram Bot работает!", "status": "OK"}

@app.get("/health/live")
async def health_live():
    return {"status": "ok"}

@app.get("/health/ready")
async def health_ready():
    try:
        if not application:
            return JSONResponse({"status": "starting"}, status_code=503)
        me = await application.bot.get_me()
        return {"status": "ready", "bot_username": me.username}
    except Exception as e:
        return JSONResponse({"status": "not_ready", "error": str(e)}, status_code=503)

@app.post("/telegram")
async def telegram_webhook(request: Request):
    # Проверка секрета в заголовке
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if TELEGRAM_WEBHOOK_SECRET and secret != TELEGRAM_WEBHOOK_SECRET:
        logger.warning("Webhook 401: секрет не совпал")
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    try:
        data = await request.json()
        if not application:
            logger.error("PTB Application ещё не инициализирован")
            return JSONResponse({"ok": False, "error": "app not ready"}, status_code=503)

        update = Update.de_json(data, application.bot)
        if update:
            await application.process_update(update)
            return {"ok": True}
        else:
            logger.warning("Получен некорректный update")
            return {"ok": False, "error": "invalid update"}
    except Exception as e:
        logger.error("❌ Ошибка обработки webhook: %s", e, exc_info=True)
        # Возвращаем 200, чтобы Telegram не засыпал ретраями
        return JSONResponse({"ok": True})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
