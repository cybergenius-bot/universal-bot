# bot.py
import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
from database import cursor, conn  # импортируем подключение из database.py

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Отсутствует TELEGRAM_TOKEN или OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

LIMIT_FREE = 5

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я GPT‑4o бот. Задай свой вопрос!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    logger.info(f"Пользователь {user_id}: {text}")

    cursor.execute("SELECT usage_count FROM user_limits WHERE user_id = %s", (user_id,))
    row = cursor.fetchone()
    count = row[0] if row else 0

    if count >= LIMIT_FREE:
        await update.message.reply_text("Вы использовали бесплатный лимит. Подписка нужна.")
        return

    if row:
        cursor.execute("UPDATE user_limits SET usage_count = usage_count + 1 WHERE user_id = %s", (user_id,))
    else:
        cursor.execute("INSERT INTO user_limits (user_id, usage_count) VALUES (%s, 1)", (user_id,))
    conn.commit()

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": text}]
        )
        answer = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка GPT‑4o: {e}")
        answer = "Ошибка GPT‑4o. Попробуй позже."

    await update.message.reply_text(answer)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Бот запущен и ожидает сообщений…")
    app.run_polling()

if __name__ == "__main__":
    main()
