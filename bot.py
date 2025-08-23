import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from openai import AsyncOpenAI
from db.py import init_db, SessionLocal, User
from payments import PayPalClient
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
paypal = PayPalClient()

TARIFFS = {"10": (100, 10), "30": (500, 30), "50": (-1, 50)}  # (messages, price)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "Привет 👋 Я GPT-бот.\nУ тебя есть 5 бесплатных сообщений.\nПосле — выбери тариф."
    keyboard = [
        [InlineKeyboardButton("💳 Купить доступ", callback_data="buy")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    async with SessionLocal() as session:
        user = await session.get(User, {"tg_id": user_id})
        if not user:
            user = User(tg_id=user_id)
            session.add(user)
            await session.commit()

        if user.free_left <= 0 and user.paid_left <= 0 and not user.is_unlimited:
            await update.message.reply_text("Лимит исчерпан. Нажми /start и выбери тариф.")
            return

        # уменьшаем лимиты
        if user.free_left > 0:
            user.free_left -= 1
        elif user.paid_left > 0:
            user.paid_left -= 1
        await session.commit()

    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": "Ты универсальный помощник."},
                  {"role": "user", "content": update.message.text}]
    )
    answer = resp.choices[0].message.content
    await update.message.reply_text(answer)


def main():
    app = Application.builder().token(settings.TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    main()
