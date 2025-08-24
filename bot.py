import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from db import get_user, decrement_messages, has_active_subscription
from config import TELEGRAM_TOKEN, WEBHOOK_URL, OPENAI_MODEL, DATABASE_URL, FREE_MESSAGES
from openai_api import openai_client  # или openai.Client в зависимости от реализации

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Привет! У тебя {FREE_MESSAGES} бесплатных сообщений.")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    await update.message.reply_text(f"Поделись этой ссылкой:\n{link}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Получено сообщение: %s", update.message.text)
    tg_id = update.effective_user.id
    user = await get_user(tg_id)
    subscribed = await has_active_subscription(tg_id)

    if subscribed or user["messages_left"] > 0:
        if not subscribed:
            await decrement_messages(tg_id)

        prompt = update.message.text
        try:
            completion = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты — GPT‑4o, универсальный ассистент."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            reply = completion.choices[0].message.content
            await update.message.reply_text(reply)
        except Exception:
            logger.exception("Ошибка при обращении к GPT")
            await update.message.reply_text("Ошибка при запросе GPT")
    else:
        keyboard = [
            [InlineKeyboardButton("20 сообщений — $10", callback_data="buy_start")],
            [InlineKeyboardButton("200 сообщений — $30", callback_data="buy_standard")],
            [InlineKeyboardButton("Безлимит — $50", callback_data="buy_premium")]
        ]
        await update.message.reply_text("У тебя закончились сообщения.", reply_markup=InlineKeyboardMarkup(keyboard))

def main():
    logger.info("Запуск бота...")
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        webhook_url=f"{WEBHOOK_URL}/bot{TELEGRAM_TOKEN}"
    )

if __name__ == "__main__":
    main()
