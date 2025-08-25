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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения (должны быть настроены в Railway)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # тот URL, куда деплоишь (например, Railway)

if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL]):
    logger.error("Не заданы переменные окружения: TELEGRAM_TOKEN, OPENAI_API_KEY, или WEBHOOK_URL")
    exit(1)

# Настройка клиента OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# Системный prompt для глубины и свободы ответов
SYSTEM_PROMPT = (
    "Ты — мощный AI‑ассистент GPT‑4.0, готов обсуждать любые темы без ограничений, "
    "от сторис и эссе до научных диссертаций и сложной математики. "
    "Отвечай максимально развёрнуто, логично и информативно."
)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот GPT‑4.0 — пиши любые запросы, от историй до диссертаций."
    )

# Обработка любых текстовых сообщений
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
        reply = response.choices[0].message.content.strip()
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error("GPT‑4.0 error: %s", e)
        await update.message.reply_text("Произошла ошибка при обращении к GPT‑4.0. Попробуйте позже.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Запускаем webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=f"/webhook/{TELEGRAM_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
    )

if __name__ == "__main__":
    main()
