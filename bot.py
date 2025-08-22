import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from database import get_user, update_user_usage, init_db, apply_plan, check_expired
from ai_handler import ask_ai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 8000))

PAYMENT_LINKS = {
    "try": "https://www.paypal.com/pay?amount=5",
    "basic": "https://www.paypal.com/pay?amount=12.99",
    "pro": "https://www.paypal.com/pay?amount=19.99"
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "👋 Привет! У тебя есть 5 бесплатных сообщений. Напиши любой вопрос."
    await update.message.reply_text(text)

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    check_expired(user_id)
    messages_left, plan, expires = get_user(user_id)

    if messages_left <= 0:
        keyboard = [
            [InlineKeyboardButton("💬 15 сообщений – $5", callback_data="try")],
            [InlineKeyboardButton("💬 300 сообщений – $12.99", callback_data="basic")],
            [InlineKeyboardButton("♾ Безлимит – $19.99", callback_data="pro")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("❗ Лимит сообщений исчерпан. Выбери тариф:", reply_markup=reply_markup)
        return

    user_msg = update.message.text
    gpt_reply = await ask_ai(user_msg)
    await update.message.reply_text(gpt_reply)
    update_user_usage(user_id)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan = query.data
    url = PAYMENT_LINKS.get(plan)
    if url:
        await query.edit_message_text(f"💳 Перейди по ссылке для оплаты:
{url}")
    else:
        await query.edit_message_text("❌ Ошибка. Попробуй снова.")

def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=WEBHOOK_URL)

if __name__ == "__main__":
    main()