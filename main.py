# main.py
import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# Логи (полезно на Render)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN env var is not set")

# --- handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Шалом! Я универсальный бот 🇮🇱.\n"
        "Команды:\n"
        "/help — помощь\n"
        "Напиши любое сообщение — я отвечу."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Пока я умею /start и /help. Скоро добавим рекламу и партнёрки.")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # временно просто эхо — проверка, что бот работает
    await update.message.reply_text(update.message.text)

def main() -> None:
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Долгий опрос — оптимально для Render (без webhook)
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
