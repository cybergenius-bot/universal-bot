import asyncio
from aiohttp import web
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

    # aiohttp сервер
    async def health(request):
        return web.Response(text="OK")

    web_app = web.Application()
    path = f"/telegram/{settings.TELEGRAM_TOKEN}"

    # Webhook для Telegram
    web_app.router.add_post(path, application.webhook_handler)
    web_app.router.add_get("/healthz", health)

    # Установка webhook
    await application.bot.set_webhook(url=f"{settings.BASE_URL}{path}")

    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.PORT)
    await site.start()

    print(f"🚀 Bot is running at {settings.BASE_URL}{path}")

    # Ждём пока жив контейнер
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
