import os
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from ai_handler import ai_reply


BOT_TOKEN = os.getenv("BOT_TOKEN")


application = ApplicationBuilder().token(BOT_TOKEN).build()


async def start(update, context):
await update.message.reply_text("Привет! Я бот и уже работаю 🔥")


application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_reply))
