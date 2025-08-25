+6
-1

import os
import logging
from aiohttp import web
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL]):
    logger.error("Отсутствуют TELEGRAM_TOKEN, OPENAI_API_KEY или WEBHOOK_URL")
    exit(1)

# OpenAI клиент
client = OpenAI(api_key=OPENAI_API_KEY)
@@ -45,34 +46,38 @@ async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_tokens=2048,
            temperature=0.8
        )
        reply = resp.choices[0].message.content.strip()
        await update.message.reply_text(reply)

    except Exception as e:
        logger.error("❌ Ошибка GPT: %s", e)
        await update.message.reply_text("⚠️ Ошибка при обращении к GPT-4o. Попробуй позже.")

# Запуск
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🚀 Запускаем webhook и удерживаем приложение активным")

    web_app = web.Application()
    web_app.router.add_get("/", lambda request: web.Response(text="ok"))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=f"/webhook/{TELEGRAM_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}"
        webhook_url=f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}",
        webhook_app=web_app,
    )

if __name__ == "__main__":
    main()
