import os
import logging
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Проверка переменных окружения
if not (TELEGRAM_TOKEN and OPENAI_API_KEY and WEBHOOK_URL):
    logger.error("Missing env vars TELEGRAM_TOKEN, OPENAI_API_KEY, or WEBHOOK_URL")
    exit(1)

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты — мощный AI-ассистент GPT‑4.0, готов отвечать на любые вопросы без цензуры, "
    "от личных историй до академических текстов — предоставляй развёрнутые, глубокие ответы."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот на GPT‑4.0. Задай любой вопрос — получишь развернутый ответ на любую тему."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info("User: %s", text)
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            max_tokens=2048,
            temperature=0.7
        )
        await update.message.reply_text(response.choices[0].message.content.strip())
    except Exception as e:
        logger.error("GPT error: %s", e)
        await update.message.reply_text("Ошибка при обращении к GPT‑4.0. Попробуй позже.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Webhook starting...")
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
    )

if __name__ == "__main__":
    main()
