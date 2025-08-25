import os
import logging
import openai
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токены и ключи
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    logger.error("Не заданы необходимые переменные окружения: TELEGRAM_TOKEN, OPENAI_API_KEY")
    exit(1)

# Настройка клиента OpenAI
openai.api_key = OPENAI_API_KEY

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот с GPT‑4.0. Напиши что-нибудь — и я отвечу максимально подробно."
    )

# Обработчик любых текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logger.info("Получено от пользователя: %s", user_text)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # технически модель называется "gpt-4"
            messages=[{"role": "user", "content": user_text}],
            max_tokens=1024,
            temperature=0.8
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Ошибка при обращении к GPT‑4.0: %s", e)
        reply = "Произошла ошибка при обращении к GPT‑4.0. Попробуй позже."

    await update.message.reply_text(reply)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запускается...")

    # Без использования asyncio.run — просто запускаем polling
    app.run_polling()

if __name__ == "__main__":
    main()
