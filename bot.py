# bot.py
import os
import logging
import asyncio
import openai
from telegram import Update
from telegram.ext import (
Application, CommandHandler, MessageHandler, filters, ContextTypes
)


# Настройки логгирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Конфигурация токенов
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # например, Railway или Render


# Настройка клиента OpenAI
openai.api_key = OPENAI_API_KEY


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! Я — бот с GPT-4.0. Задай мне любой вопрос.")


# Обработка сообщений пользователя
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_message = update.message.text
logger.info("Received message: %s", user_message)


try:
response = openai.ChatCompletion.create(
model="gpt-4",
messages=[{"role": "user", "content": user_message}]
)
reply_text = response.choices[0].message.content.strip()
except Exception as e:
logger.error("OpenAI error: %s", e)
reply_text = "Произошла ошибка при обращении к GPT-4.0. Попробуйте позже."


await update.message.reply_text(reply_text)


# Запуск бота
def main():
app = Application.builder().token(TELEGRAM_TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


logger.info("Starting bot...")
app.run_webhook(
listen="0.0.0.0",
port=int(os.getenv("PORT", 8080)),
webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
)


if __name__ == "__main__":
asyncio.run(main())
