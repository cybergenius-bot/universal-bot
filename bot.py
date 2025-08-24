import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import settings
from db import init_db


async def start_handler(update, context):
    await update.message.reply_text("✅ Бот работает через webhook!")


async def echo_handler(update, context):
    await update.message.reply_text(f"Вы написали: {update.message.text}")


async def main():
    # Инициализация БД
    await init_db()

    # Создаём Telegram приложение
    application = Application.builder().token(settings.TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))

    # Запуск в webhook-режиме
    await application.run_webhook(
        listen="0.0.0.0",
        port=settings.PORT,
        url_path="telegram",  # ← важно: должен совпадать с route
        webhook_url=f"{settings.BASE_URL}/telegram",
    )


if __name__ == "__main__":
    asyncio.run(main())
