import os
import logging
import asyncio
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI


# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
raise ValueError("Отсутствует TELEGRAM_TOKEN или OPENAI_API_KEY")


# OpenAI клиент
client = OpenAI(api_key=OPENAI_API_KEY)


# SQLite база
conn = sqlite3.connect("usage.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS usage (
user_id INTEGER PRIMARY KEY,
count INTEGER DEFAULT 0,
updated_at TEXT
)
""")
conn.commit()


LIMIT_FREE = 5


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! Я GPT‑4o бот. Задай вопрос!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
message = update.message.text.strip()
logger.info(f"Пользователь: {message}")


cursor.execute("SELECT count FROM usage WHERE user_id = ?", (user_id,))
row = cursor.fetchone()
count = row[0] if row else 0


if count >= LIMIT_FREE:
await update.message.reply_text("Вы исчерпали бесплатный лимит. Для продолжения — оформите подписку.")
return


try:
response = client.chat.completions.create(
model="gpt-4o",
messages=[{"role": "user", "content": message}]
)
answer = response.choices[0].message.content.strip()
except Exception as e:
logger.error(f"Ошибка GPT‑4o: {e}")
answer = "Ошибка GPT‑4o. Попробуй позже."


await update.message.reply_text(answer)


if row:
cursor.execute("UPDATE usage SET count = count + 1, updated_at = ? WHERE user_id = ?", (datetime.now(), user_id))
else:
cursor.execute("INSERT INTO usage (user_id, count, updated_at) VALUES (?, 1, ?)", (user_id, datetime.now()))
conn.commit()


if __name__ == "__main__":
app = Application.builder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
