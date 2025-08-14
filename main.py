import os
from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# === Обязательные переменные окружения ===
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]          # токен от BotFather
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "123-ABC")  # та же строка, что в setWebhook URL

# === Telegram application ===
tg_app = Application.builder().token(TELEGRAM_TOKEN).build()

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я на вебхуке и готов отвечать 👋")

async def echo_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or ""
    await update.message.reply_text(f"Ты написал: {text}")

tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_text))

# === FastAPI ===
app = FastAPI(title="Universal Bot (webhook)")

@app.get("/health")
async def health():
    return {"ok": True}

# РОВНО этот путь должен совпадать с тем, что ты ставишь в setWebhook
@app.post(f"/webhook/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update = Update.de_json(data, tg_app.bot)
    # Обрабатываем апдейт так, будто он пришёл в апликейшн
    await tg_app.process_update(update)
    return {"ok": True}
    await application.stop()
    return {"ok": True}

# Инициализация PTB один раз (без polling!)
@app.on_event("startup")
async def on_startup():
    await tg.initialize()
