# bot.py
import asyncio
from aiohttp import web
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import settings
from db import init_db
from payments import PayPalClient

# Пример handler'ов, реализуйте по вашему коду
async def start_handler(update, context):
    await update.message.reply_text("Привет! Я универсальный бот.")

async def message_handler(update, context):
    await update.message.reply_text("Вы написали: " + update.message.text)

async def main():
    await init_db()

    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    async def health(request):
        return web.Response(text="OK")

    web_app = web.Application()
    path = f"/telegram/{settings.TELEGRAM_TOKEN}"
    web_app.router.add_post(path, app.webhook_handler)
    web_app.router.add_get("/healthz", health)

    await app.bot.set_webhook(url=f"{settings.BASE_URL}{path}")

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.PORT)
    await site.start()

    print(f"Webhook set to {settings.BASE_URL}{path}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
