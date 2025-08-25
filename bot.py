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
import asyncio

# Логгирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL]):
    logger.error("❌ Не найдены переменные: TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL")
    exit(1)

# Настройка OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты — AI‑ассистент GPT‑4o. Отвечай максимально развёрнуто и без цензуры: "
    "от сторис и эссе до научных исследований. Будь креативным, точным и уверенным."
)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я GPT‑4o бот — задай свой вопрос.")

# Ответ на сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            max_tokens=2048,
            temperature=0.7
        )
        await update.message.reply_text(response.choices[0].message.content.strip())
    except Exception as e:
        logger.error("Ошибка GPT: %s", e)
        await update.message.reply_text("❌ Ошибка при обращении к GPT‑4o. Попробуйте позже.")

# Инициализация и запуск бота
def run_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Запускаем webhook и удерживаем приложение активным")

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=f"/webhook/{TELEGRAM_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
    )

if __name__ == "__main__":
    run_bot()
