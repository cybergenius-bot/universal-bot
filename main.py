import os
import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder,
    CommandHandler, MessageHandler, ContextTypes, filters
)

# ==== ЛОГИ ====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("universal-bot")

# ==== ENV ====
BOT_TOKEN     = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL   = os.getenv("WEBHOOK_URL")  # например https://universal-bot-production.up.railway.app
PORT          = int(os.getenv("PORT", "8080"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("Нет BOT_TOKEN в переменных окружения.")

# ==== OpenAI (опционально) ====
use_ai = False
ai_client = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        ai_client = OpenAI(api_key=OPENAI_API_KEY)
        use_ai = True
        log.info("OpenAI подключен.")
    except Exception as e:
        log.warning("OpenAI не инициализировался: %s", e)

# ==== Telegram Application ====
application: Application = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Handlers ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Пиши вопрос — отвечу. "
        "Команды: /help"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступно:\n"
        "• Отправь текст — получишь ответ\n"
        "• Стикеры/голос/видео — принимаю, но не обрабатываю\n"
        "• /start, /help"
    )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # Если есть OpenAI — даём «умный» ответ
    if use_ai and ai_client:
        try:
            completion = ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Кратко и по делу, по-русски."},
                    {"role": "user", "content": text},
                ],
                temperature=0.6,
                max_tokens=400,
            )
            answer = completion.choices[0].message.content.strip()
        except Exception as e:
            log.exception("OpenAI error: %s", e)
            answer = "Не смог получить ответ от ИИ, попробуй ещё раз."
    else:
        # Без ИИ — простой полезный ответ (НЕ эхо)
        answer = (
            "Я работаю! Сейчас режим без ИИ. "
            "Добавь переменную окружения OPENAI_API_KEY, чтобы включить умные ответы."
        )

    await update.message.reply_text(answer, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Не падаем на медиа, отвечаем мягко
    await update.message.reply_text("Медиа получил 👍. Текстовый вопрос — в ответ дам информацию.")

# Регистрируем обработчики
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
application.add_handler(MessageHandler(filters.VOICE | filters.VIDEO | filters.PHOTO | filters.Document.ALL, media_handler))

# ==== FastAPI ====
app = FastAPI(title="Universal Bot")

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "OK"

@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Принимаем апдейты от Telegram и передаём в PTB."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "bad json"}, status_code=400)

    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})

@app.on_event("startup")
async def on_startup():
    # Запускаем PTB-приложение и ставим webhook:
    await application.initialize()
    await application.start()

    if not WEBHOOK_URL:
        log.warning("WEBHOOK_URL не задан: вебхук не будет установлен.")
    else:
        url = WEBHOOK_URL.rstrip("/") + "/telegram"
        await application.bot.set_webhook(url=url, drop_pending_updates=True)
        log.info("Webhook set to %s", url)

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await application.bot.delete_webhook()
    except Exception:
        pass
    await application.stop()
    await application.shutdown()
    log.info("Webhook set to %s", url)

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()
