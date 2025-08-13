import os
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)
# ===== Настройки из окружения =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not RAILWAY_URL:
    raise RuntimeError("RAILWAY_URL is not set")

# ===== Инициализация FastAPI и Telegram Application =====
app = FastAPI(title="universal-bot")
tg_app = Application.builder().token(TOKEN).build()

# ===== Handlers =====
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Пиши любой вопрос — отвечу. "
        "Фото/видео/голос — тоже принимаю."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — приветствие\n"
        "Просто напиши вопрос — получишь ответ.\n"
        "Отправь фото/видео/голос — я их приму и отвечу."
    )

# ——— Текст через OpenAI (асинхронно, безопасно для Railway) ———
async def ai_answer(prompt: str) -> str:
    if not OPENAI_API_KEY:
        return "OpenAI API ключ не задан."
    # Ленивая загрузка клиента, чтобы не тащить лишнее при импорте
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Вынесем вызов в отдельный поток, чтобы не блокировать event loop
    def _call():
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты дружелюбный ассистент, отвечай кратко и по делу."},
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
        reply = f"Не удалось получить ответ ИИ: {e}"
    await update.message.reply_text(reply)

# ——— Базовые обработчики медиа (подтверждают приём) ———
async def photo_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Фото получил! Спасибо 🙌")

async def video_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Видео получил! Спасибо 🎬")

async def voice_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Голосовое получил! 🎤")

# Регистрируем хендлеры
tg_app.add_handler(CommandHandler("start", start_cmd))
tg_app.add_handler(CommandHandler("help", help_cmd))
tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_msg))
tg_app.add_handler(MessageHandler(filters.PHOTO, photo_msg))
tg_app.add_handler(MessageHandler(filters.VIDEO, video_msg))
tg_app.add_handler(MessageHandler(filters.VOICE, voice_msg))

# ===== Webhook =====
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{RAILWAY_URL}{WEBHOOK_PATH}"

@app.on_event("startup")
async def on_startup():
    # Ставим вебхук при запуске контейнера
    await tg_app.bot.set_webhook(WEBHOOK_URL)
    print(f"[OK] Webhook set: {WEBHOOK_URL}")

@app.on_event("shutdown")
async def on_shutdown():
    # Аккуратное выключение, без конфликтов event loop
    await tg_app.shutdown()
    await tg_app.stop()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(req: Request):
    data = await req.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return JSONResponse({"ok": True})

@app.get("/")
def health():
    return PlainTextResponse("universal-bot: OK")
