from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import settings
from db import init_db


async def start_handler(update, context):
    await update.message.reply_text("✅ Бот работает через webhook!")


async def echo_handler(update, context):
    await update.message.reply_text(f"Вы написали: {update.message.text}")


async def post_init(application):
    await init_db()


def main():
    application = Application.builder().token(settings.TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo_handler))

    application.run_webhook(
        listen="0.0.0.0",
        port=settings.PORT,
        url_path="telegram",
        webhook_url=f"{settings.BASE_URL}/telegram",
    )


if __name__ == "__main__":
    main()
