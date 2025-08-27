import os
import logging
import psycopg2
import datetime
import openai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters


# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")


# Подключение к базе данных
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()


# Создание таблицы пользователей (если не существует)
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
id BIGINT PRIMARY KEY,
message_count INTEGER DEFAULT 0,
limit_type TEXT DEFAULT 'free',
last_reset TIMESTAMP DEFAULT NOW()
);
''')
conn.commit()


# Проверка лимита
async def check_limit(user_id: int) -> bool:
cursor.execute("SELECT message_count, limit_type, last_reset FROM users WHERE id = %s", (user_id,))
result = cursor.fetchone()


now = datetime.datetime.utcnow()


if result is None:
cursor.execute("INSERT INTO users (id) VALUES (%s)", (user_id,))
conn.commit()
return True


message_count, limit_type, last_reset = result


# Сброс лимитов каждые 24 часа для free пользователей
if limit_type == 'free' and (now - last_reset).total_seconds() > 86400:
cursor.execute("UPDATE users SET message_count = 0, last_reset = %s WHERE id = %s", (now, user_id))
