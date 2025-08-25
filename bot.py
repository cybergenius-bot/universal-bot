import os
import logging
import asyncio
import openai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токены
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Клиент OpenAI
openai.api_key = OPENAI_API_KEY

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот на GPT-4.0. Задай мне любой вопрос!")

# Ответ на сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    logger.info("📩 User: %s", user_text)

    try:
        response = openai.chat.completions.create(
            model="gpt-4.0",
            messages=[{"role": "user", "content": user_text}],
            max_tokens=800,   # расширенные ответы
            temperature=0.8
        )

        bot_reply = response.choices[0].message.content
        await update.message.reply_text(bot_reply)

    except Exception as e:
        logger.error("Ошибка GPT: %s", e)
        await update.message.reply_text("⚠️ Ошибка при запросе к GPT-4.0.")

def launch_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app

async def main():
    app = launch_bot()
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
