import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Получение токенов из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not WEBHOOK_URL:
raise ValueError("Отсутствует TELEGRAM_TOKEN, OPENAI_API_KEY или WEBHOOK_URL")


client = OpenAI(api_key=OPENAI_API_KEY)


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! Я GPT-4o бот. Задай вопрос!")


# Ответ на сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_message = update.message.text
try:
response = client.chat.completions.create(
model="gpt-4o",
messages=[
{"role": "user", "content": user_message}
]
)
reply = response.choices[0].message.content
except Exception as e:
logger.error(f"Ошибка GPT-4o: {e}")
reply = "Ошибка GPT‑4o. Попробуй позже."


await update.message.reply_text(reply)


# Основной запуск бота
async def main():
application = Application.builder().token(TELEGRAM_TOKEN).build()


# Регистрируем команды и обработчики
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# Настройка webhook
await application.bot.delete_webhook()
await application.bot.set_webhook(url=WEBHOOK_URL)


logger.info("Бот запущен через webhook")
await application.run_webhook(
listen="0.0.0.0",
port=int(os.getenv("PORT", "8000")),
webhook_url=WEBHOOK_URL
)


if __name__ == '__main__':
import asyncio
asyncio.run(main())
