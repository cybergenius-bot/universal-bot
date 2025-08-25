import os
import logging
import asyncio
import openai
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from db import get_user, decrement_messages, has_active_subscription
from config import TELEGRAM_TOKEN, WEBHOOK_URL, OPENAI_MODEL, OPENAI_API_KEY, FREE_MESSAGES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Привет! Бесплатных сообщений: {FREE_MESSAGES}")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    await update.message.reply_text(f"Поделись:\n{link}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🆕 Message received: %s", update.message.text)
    await update.message.reply_text("✅ Got your message!")  # Тестовый ответ

def launch_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app

async def main():
    app = launch_bot()
    await app.initialize()
    await app.start()

    # Убедись, что WEBHOOK_URL начинается с https:// и не содержит слеш в конце
    webhook_path = f"/webhook/{TELEGRAM_TOKEN}"
    full_webhook_url = WEBHOOK_URL.rstrip("/") + webhook_path

    await app.bot.set_webhook(full_webhook_url)
    logger.info("🚀 Webhook set to: %s", full_webhook_url)

    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        url_path=webhook_path
    )

    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(main())
