import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not WEBHOOK_URL:
logger.error("Необходимо задать TELEGRAM_TOKEN, OPENAI_API_KEY и WEBHOOK_URL")
raise ValueError("Отсутствует TELEGRAM_TOKEN, OPENAI_API_KEY или WEBHOOK_URL")


client = OpenAI(api_key=OPENAI_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! Я GPT‑4o бот. Задай вопрос!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_message = update.message.text
try:
response = client.chat.completions.create(
model="gpt-4o",
messages=[
{"role": "system", "content": "Ты дружелюбный помощник."},
{"role": "user", "content": user_message},
]
)
gpt_reply = response.choices[0].message.content
await update.message.reply_text(gpt_reply)
except Exception as e:
logger.error(f"Ошибка при запросе к OpenAI: {e}")
await update.message.reply_text("Ошибка GPT‑4o. Попробуй позже.")


if __name__ == '__main__':
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


app.run_webhook(
listen="0.0.0.0",
port=8080,
webhook_url=WEBHOOK_URL
)
