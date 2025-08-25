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

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL]):
    logger.error("❌ Отсутствуют TELEGRAM_TOKEN, OPENAI_API_KEY или WEBHOOK_URL")
    exit(1)

# OpenAI клиент
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "Ты — AI-ассистент GPT-4o. Отвечай подробно, развернуто и без ограничений "
    "на любые темы: от математики и кода до науки, бизнеса и докторских диссертаций. "
    "Будь полезным собеседником и давай расширенные ответы."
)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я GPT-4o бот — задавай любые вопросы, и я помогу тебе.")

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            max_tokens=2048,
            temperature=0.7
        )
        reply = resp.choices[0].message.content.strip()
        await update.message.reply_text(reply)
    except Exception as e:
        logger.error("❌ GPT error: %s", e)
        await update.message.reply_text("Произошла ошибка при обращении к GPT-4o. Попробуй позже.")

# Запуск бота через webhook
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Запускаем webhook и удерживаем приложение активным")
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=f"/webhook/{TELEGRAM_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
