import os
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ---------- ЛОГИ ----------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("universal-bot")

# ---------- ENV ----------
TOKEN = os.getenv("TELEGRAM_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")   # напр.: https://universal-bot-production.up.railway.app
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not RAILWAY_URL or not RAILWAY_URL.startswith("http"):
    raise RuntimeError(f"RAILWAY_URL is not set or invalid: {RAILWAY_URL}")

# ---------- FastAPI + PTB ----------
app = FastAPI(title="universal-bot")
tg_app = Application.builder().token(TOKEN).build()

# ---------- Handlers ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Пиши вопрос, присылай фото/видео/голос — отвечу."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — приветствие\n"
        "Просто напиши вопрос — получишь ответ.\n"
        "Фото/видео/голос — принимаю и отвечаю."
    )

async def ai_answer(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return "OpenAI API ключ не задан."
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    def _call():
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Отвечай кратко и по делу, дружелюбно."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=600,
        )
        return resp.choices[0].message.content.strip()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _call)

async def text_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    try:
        reply = await ai_answer(user_text)
    except Exception as e:
        log.exception("AI error")
        reply = f"Не удалось получить ответ ИИ: {e}"
    await update.message.reply_text(reply)

async def photo_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Фото получил! 🙌")

async def video_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Видео получил! 🎬")

async def voice_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Голосовое получил! 🎤")

tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(CommandHandler("help", help_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_msg))
tg_app.add_handler(MessageHandler(filters.PHOTO, photo_msg))
tg_app.add_handler(MessageHandler(filters.VIDEO, video_msg))
tg_app.add_handler(MessageHandler(filters.VOICE, voice_msg))

# ---------- Webhook ----------
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RAILWAY_URL}{WEBHOOK_PATH}"

@app.on_event("startup")
async def on_startup():
    # ВАЖНО: корректный жизненный цикл PTB при вебхуке
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.bot.set_webhook(
        WEBHOOK_URL,
        allowed_updates=["message", "callback_query", "chat_member", "my_chat_member"],
    )
    log.info(f"Webhook set to: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await tg_app.bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass
    await tg_app.stop()
    await tg_app.shutdown()
    log.info("Bot stopped gracefully.")

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return JSONResponse({"ok": True})

@app.get("/")
def health():
    return PlainTextResponse("universal-bot: OK")
