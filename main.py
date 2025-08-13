# main.py
import os
import logging
from typing import Final
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("universal-bot")

# --- ENV ---
TOKEN: Final[str] = os.getenv("TELEGRAM_TOKEN", "")
if not TOKEN:
    raise RuntimeError("No TELEGRAM_TOKEN provided")

PORT: int = int(os.getenv("PORT", "8080"))

# Полный публичный домен Railway БЕЗ слэша на конце,
# например: https://universal-bot-production.up.railway.app
WEBHOOK_BASE: str = os.getenv("WEBHOOK_URL", "").rstrip("/")

# Можно оставить по умолчанию
WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "webhook")


# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Бот запущен ✅ Пиши — отвечу.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text or ""
    await update.message.reply_text(f"Ты написал: {txt}")


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    if WEBHOOK_BASE:
        # Синхронная обёртка — сама настроит и поднимет вебхук и event loop.
        webhook_url = f"{WEBHOOK_BASE}/{WEBHOOK_PATH}"
        log.info("Run webhook on %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        # Режим поллинга для локальных тестов
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
