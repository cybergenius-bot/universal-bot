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
        conn.commit()
        return True

    # Ограничения
    limits = {
        'free': 5,
        'basic': 20,
        'pro': 200,
        'unlimited': float('inf')
    }

    return message_count < limits.get(limit_type, 5)

# Увеличение счётчика сообщений
def increment_usage(user_id: int):
    cursor.execute("UPDATE users SET message_count = message_count + 1 WHERE id = %s", (user_id,))
    conn.commit()

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    if not await check_limit(user_id):
        await update.message.reply_text("Вы превысили лимит запросов. Пожалуйста, оформите подписку.")
        return

    openai.api_key = OPENAI_API_KEY

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": user_message}]
        )
        bot_reply = response.choices[0].message.content
        await update.message.reply_text(bot_reply)
        increment_usage(user_id)

    except Exception as e:
        logger.error(f"Ошибка GPT: {e}")
        await update.message.reply_text("Произошла ошибка при обращении к GPT-4o. Попробуйте позже.")

# Обработка /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я GPT‑4o бот. Задай вопрос!")

# Запуск бота
if __name__ == '__main__':
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not DATABASE_URL:
        raise ValueError("Отсутствует TELEGRAM_TOKEN, OPENAI_API_KEY или DATABASE_URL")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен")
    app.run_polling()
