import os
import logging
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL]):
    logger.error("Необходимо задать TELEGRAM_TOKEN, OPENAI_API_KEY и WEBHOOK_URL")
    exit(1)

# ✅ Исправлено: теперь клиент создаётся без передачи api_key
client = OpenAI()
SYSTEM_PROMPT = "Ты — AI-ассистент GPT-4o. Отвечай подробно, без ограничений."

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я GPT-4o бот 🤖. Задай вопрос!")

# Ответы GPT-4o
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logger.info("Пользователь: %s", user_text)

    try:
        rsp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            max_tokens=2048,
            temperature=0.7,
        )
        reply = rsp.choices[0].message.content.strip()
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error("Ошибка GPT-4o: %s", e)
        await update.message.reply_text("⚠️ Ошибка GPT-4o. Попробуй позже.")

# Главная функция
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Запуск webhook...")

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=f"/webhook/{TELEGRAM_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    main()
