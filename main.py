import os
import asyncio
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

# ====== Хендлеры ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот на webhook. Напиши мне что‑нибудь 👋"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Пока просто эхо, чтобы проверить стабильность webhook.
    # Позже сюда добавим ИИ‑ответы, фото/видео, оплату и т.д.
    text = update.message.text or ""
    await update.message.reply_text(f"Ты написал: {text}")

# ====== Запуск приложения с webhook ======
async def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Регистрируем хендлеры
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Порт Railway
    port = int(os.environ.get("PORT", 8000))

    # Твой публичный URL для webhook (добавим в переменные Railway)
    webhook_url = os.environ["WEBHOOK_URL"]  # например: https://universal-bot-production.up.railway.app/telegram

    # Запускаем встроенный aiohttp‑сервер и одновременно ставим webhook в Telegram
    await app.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_url=webhook_url,
        drop_pending_updates=True,
    )

if __name__ == "__main__":
    asyncio.run(main())
