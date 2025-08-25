import os
import logging
import asyncio
import openai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)
from db import get_user, decrement_messages, has_active_subscription
from config import (
    TELEGRAM_TOKEN,
    WEBHOOK_URL,
    OPENAI_MODEL,
    OPENAI_API_KEY,
    FREE_MESSAGES
)

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка OpenAI клиента
openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Привет! У тебя {FREE_MESSAGES} бесплатных сообщений.")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
    await update.message.reply_text(f"🎁 Поделись этим ботом:\n{link}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Получено сообщение: %s", update.message.text)
    # Тестовый лог-ответ для проверки
    await update.message.reply_text("✅ Bot got your message!")  

    tg_id = update.effective_user.id
    user = await get_user(tg_id)
    subscribed = await has_active_subscription(tg_id)

    if subscribed or user["messages_left"] > 0:
        if not subscribed:
            await decrement_messages(tg_id)
        prompt = update.message.text.strip()
        try:
            completion = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты универсальный GPT‑4o ассистент."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            reply = completion.choices[0].message.content
            await update.message.reply_text(reply)
        except Exception:
            logger.exception("Ошибка при обращении к GPT")
            await update.message.reply_text("❌ Ошибка при обращении к GPT.")
    else:
        keyboard = [
            [InlineKeyboardButton("20 запросов – $10", callback_data="buy_start")],
            [InlineKeyboardButton("200 запросов – $30", callback_data="buy_standard")],
            [InlineKeyboardButton("Безлимит – $50", callback_data="buy_premium")]
        ]
        await update.message.reply_text(
            "У тебя закончились запросы. Выбери тариф:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def run_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

    await app.initialize()
    await app.start()
    logger.info("🚀 Bot started successfully")

    webhook_path = f"/webhook/{TELEGRAM_TOKEN}"
    await app.bot.set_webhook(WEBHOOK_URL + webhook_path)
    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        url_path=webhook_path
    )

    await app.updater.idle()

if __name__ == "__main__":
    asyncio.run(run_bot())
