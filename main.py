import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

# ====== ENV ======
BOT_TOKEN   = os.environ["TELEGRAM_TOKEN"]
PUBLIC_URL  = os.environ["RAILWAY_URL"]  # например: https://universal-bot-production.up.railway.app
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"   # уникальный путь
WEBHOOK_URL  = f"{PUBLIC_URL}{WEBHOOK_PATH}"

# ====== Telegram Application ======
tg = Application.builder().token(BOT_TOKEN).build()

# --- handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я универсальный бот. Пиши текст, присылай фото/видео/voice.")

async def echo_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Фото получил ✅")

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Видео получил ✅")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Голосовое получил ✅")

tg.add_handler(CommandHandler("start", start))
tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_text))
tg.add_handler(MessageHandler(filters.PHOTO, handle_photo))
tg.add_handler(MessageHandler(filters.VIDEO, handle_video))
tg.add_handler(MessageHandler(filters.VOICE, handle_voice))

# ====== FastAPI app ======
app = FastAPI()

@app.on_event("startup")
async def on_startup():
    # ВАЖНО: правильная последовательность для PTB v20+
    await tg.initialize()
    await tg.bot.set_webhook(WEBHOOK_URL)   # ставим вебхук на наш путь
    await tg.start()
    # updater не используем; апдейты будут идти POST'ом в эндпоинт ниже

@app.on_event("shutdown")
async def on_shutdown():
    await tg.stop()
    await tg.shutdown()

# Приём апдейтов от Telegram
@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg.bot)
    await tg.process_update(update)
    return {"ok": True}

# Простой healthcheck (можно указать в Railway)
@app.get("/")
async def root():
    return {"status": "ok"}
