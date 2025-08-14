import os
import tempfile
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler, ContextTypes, filters
)
from pydub import AudioSegment

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]                 # токен бота
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "123-ABC")  # секрет в URL
# При желании добавишь OPENAI_API_KEY и т.п.

app = FastAPI(title="Universal Bot")

# --- Telegram Application (без polling, только webhook) ---
tg = Application.builder().token(TELEGRAM_TOKEN).build()

# Команда /start — проверка, что ответы идут
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я на Railway по веб-хуку ✅")

# Эхо текста (для проверки цепочки)
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Получил: {update.message.text}")

# Фото — просто подтверждаем и показываем URL файла Telegram
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    await update.message.reply_text(f"Фото получено. URL: {file.file_path}")

# Голос — конвертация .ogg -> .mp3 (через pydub + imageio-ffmpeg)
async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    t_ogg = tempfile.mktemp(suffix=".ogg")
    t_mp3 = tempfile.mktemp(suffix=".mp3")
    tg_file = await voice.get_file()
    await tg_file.download_to_drive(t_ogg)
    AudioSegment.from_file(t_ogg).export(t_mp3, format="mp3")
    await update.message.reply_text("Голосовое получено и сконвертировано в mp3 ✅")

# Регистрируем обработчики
tg.add_handler(CommandHandler("start", cmd_start))
tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
tg.add_handler(MessageHandler(filters.PHOTO, on_photo))
tg.add_handler(MessageHandler(filters.VOICE, on_voice))

# --- FastAPI маршруты ---
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="bad secret")
    data = await request.json()
    update = Update.de_json(data, tg.bot)
    await tg.process_update(update)
    return {"ok": True}

# Инициализация PTB один раз (без polling!)
@app.on_event("startup")
async def on_startup():
    await tg.initialize()
