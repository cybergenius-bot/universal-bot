# main.py
import os
import logging
from typing import Final

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
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

# Для Railway:
PORT: int = int(os.getenv("PORT", "8080"))

# Вставь сюда полный публичный URL сервиса Railway (без завершающего /),
# например: https://universal-bot-production.up.railway.app
WEBHOOK_BASE: str = os.getenv("WEBHOOK_URL", "").rstrip("/")

# Секретный путь вебхука (можно оставить по умолчанию)
WEBHOOK_PATH: str = os.getenv("WEBHOOK_PATH", "webhook")

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Бот запущен ✅\nПиши обычный текст — отвечу.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Пока для проверки — просто эхо.
    # (Позже сюда подключим ИИ‑ответы, фото/видео и т.д.)
    text = update.message.text or ""
    await update.message.reply_text(f"Ты написал: {text}")

def build_app() -> Application:
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    return app

async def main_async() -> None:
    app = build_app()

    if WEBHOOK_BASE:
        # Вебхук режим (Railway)
        webhook_url = f"{WEBHOOK_BASE}/{WEBHOOK_PATH}"
        log.info("Setting webhook to %s", webhook_url)
        await app.bot.set_webhook(webhook_url)

        # PTB сам поднимет aiohttp‑сервер на указанном пути
        await app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=webhook_url,
            drop_pending_updates=True,
        )
    else:
        # Поллинг (на всякий случай)
        await app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main_async())
    except RuntimeError as e:
        # Обход "Cannot close a running event loop" (особенности окружения)
        if "Cannot close a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main_async())
        else:
            raise
