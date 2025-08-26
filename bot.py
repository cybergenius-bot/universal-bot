import logging
import os

from aiohttp import web
from openai import AsyncOpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
OPENAI_API_KEY = settings.OPENAI_API_KEY
WEBHOOK_URL = settings.WEBHOOK_URL

if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL]):
    raise SystemExit("Missing TELEGRAM_TOKEN, OPENAI_API_KEY or WEBHOOK_URL")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты — AI-ассистент GPT-4o. Отвечай максимально развёрнуто и без цензуры: "
    "от сторис и эссе до сложных научных работ. Будь собеседником, учёным, "
    "помощником в любых темах."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text("👋 Привет! Я GPT-4o бот. Задай мне любой вопрос!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to user messages via OpenAI Chat Completions."""
    user_text = update.message.text
    logger.info("📩 Пользователь: %s", user_text)
    try:
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_tokens=2048,
            temperature=0.8,
        )
        reply = resp.choices[0].message.content.strip()
        await update.message.reply_text(reply)
    except Exception as exc:  # pragma: no cover - network errors
        logger.error("❌ Ошибка GPT: %s", exc)
        await update.message.reply_text("⚠️ Ошибка при обращении к GPT. Попробуй позже.")

def main() -> None:
    """Start the Telegram bot using webhook mode."""
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    web_app = web.Application()
    web_app.router.add_get("/", lambda request: web.Response(text="ok"))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=f"/webhook/{TELEGRAM_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        webhook_app=web_app,
    )

if __name__ == "__main__":
    main()
