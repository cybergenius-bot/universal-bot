import logging
import os
import sqlite3
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI


# Логгирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Настройки из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GPT_MODEL = "gpt-4o"


if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
raise ValueError("Отсутствует TELEGRAM_TOKEN или OPENAI_API_KEY")


client = OpenAI(api_key=OPENAI_API_KEY)


# База данных
conn = sqlite3.connect("users.db")
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
user_id INTEGER PRIMARY KEY,
questions_left INTEGER DEFAULT 5
)
''')
conn.commit()


# Обработка команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
conn.commit()
await update.message.reply_text("Привет! Я GPT‑4o бот. Задай вопрос!")


# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
cursor.execute("SELECT questions_left FROM users WHERE user_id = ?", (user_id,))
row = cursor.fetchone()
if row is None:
questions_left = 5
cursor.execute("INSERT INTO users (user_id, questions_left) VALUES (?, ?)", (user_id, questions_left))
conn.commit()
else:
questions_left = row[0]


if questions_left <= 0:
await update.message.reply_text("Вы исчерпали лимит. Пополните баланс для продолжения.")
return


cursor.execute("UPDATE users SET questions_left = questions_left - 1 WHERE user_id = ?", (user_id,))
conn.commit()


try:
response = client.chat.completions.create(
model=GPT_MODEL,
messages=[{"role": "user", "content": update.message.text}]
)
answer = response.choices[0].message.content
except Exception as e:
logger.error(f"Ошибка GPT: {e}")
answer = "Ошибка GPT‑4o. Попробуй позже."


await update.message.reply_text(answer)


# Запуск бота
async def main():
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))


await app.run_polling()


if __name__ == '__main__':
import asyncio
asyncio.run(main())
