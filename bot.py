import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
import psycopg2


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Получение токенов и ключей
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
raise ValueError("Отсутствует TELEGRAM_TOKEN или OPENAI_API_KEY")


# Инициализация OpenAI клиента
client = OpenAI(api_key=OPENAI_API_KEY)


# Подключение к PostgreSQL
conn = psycopg2.connect(
dbname=os.getenv("PGDATABASE"),
user=os.getenv("PGUSER"),
password=os.getenv("PGPASSWORD"),
host=os.getenv("PGHOST"),
port=os.getenv("PGPORT")
)
cursor = conn.cursor()


# Создание таблицы, если нет
cursor.execute('''
CREATE TABLE IF NOT EXISTS user_limits (
user_id BIGINT PRIMARY KEY,
usage_count INT DEFAULT 0
)
''')
conn.commit()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! Я GPT‑4o бот. Задай вопрос!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_id = update.effective_user.id
user_text = update.message.text


cursor.execute("SELECT usage_count FROM user_limits WHERE user_id = %s", (user_id,))
row = cursor.fetchone()


if row:
usage_count = row[0]
if usage_count >= 5:
await update.message.reply_text("Вы использовали бесплатный лимит. Чтобы продолжить, оформите подписку.")
return
cursor.execute("UPDATE user_limits SET usage_count = usage_count + 1 WHERE user_id = %s", (user_id,))
else:
cursor.execute("INSERT INTO user_limits (user_id, usage_count) VALUES (%s, 1)", (user_id,))
conn.commit()


try:
response = client.chat.completions.create(
model="gpt-4o",
messages=[{"role": "user", "content": user_text}]
)
reply_text = response.choices[0].message.content
except Exception as e:
logger.error(f"Ошибка GPT‑4o: {e}")
reply_text = "Ошибка GPT‑4o. Попробуй позже."


await update.message.reply_text(reply_text)


if __name__ == '__main__':
app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.run_polling()
