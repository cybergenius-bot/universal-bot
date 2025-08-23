import os
import asyncio
import logging
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes
)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

application = ApplicationBuilder().token(BOT_TOKEN).build()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот и уже работаю 🔥")

application.add_handler(CommandHandler("start", start))

# Храним флаг, проинициализирован ли бот
bot_ready = False

# webhook endpoint
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    global bot_ready
    if not bot_ready:
        return "Bot not initialized yet", 503

    update = Update.de_json(request.get_json(force=True), application.bot)
    asyncio.run(application.process_update(update))
    return "OK"

# Основной запуск
if __name__ == "__main__":
    async def main():
        global bot_ready
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(url=WEBHOOK_URL)
        bot_ready = True
        logging.info("✅ Бот запущен и Webhook установлен")

    asyncio.run(main())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
