import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import requests

# =====================
# Настройки
# =====================
TOKEN = os.getenv("BOT_TOKEN")  # Токен берём из переменной окружения на Railway
WEBHOOK_URL = f"https://universal-bot-production.up.railway.app/webhook"  # Твой домен Railway

# =====================
# Логирование
# =====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =====================
# Команды бота
# =====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Бот работает через вебхук 🚀")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# =====================
# Основной запуск
# =====================
def main():
    # 1. Устанавливаем вебхук на Telegram API
    r = requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}")
    logging.info(f"Webhook set result: {r.json()}")

    # 2. Создаём приложение
    application = ApplicationBuilder().token(TOKEN).updater(None).build()

    # 3. Регистрируем команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # 4. Запускаем Webhook сервер
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        url_path="webhook",
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()
