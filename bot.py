import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, CommandHandler, filters


# Настройка логирования
logging.basicConfig(
level=logging.INFO,
format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Получение токена и URL
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


if not TOKEN:
raise ValueError("TELEGRAM_TOKEN не установлен!")
if not WEBHOOK_URL:
raise ValueError("WEBHOOK_URL не установлен!")


# Создание бота и приложения
bot = Bot(token=TOKEN)
application = Application.builder().token(TOKEN).build()


# Обработчики команд
async def start_command(update: Update, context):
user = update.effective_user
welcome_text = f"Привет, {user.first_name}! \U0001F44B\n\nЯ телеграм бот. Как дела?"
await update.message.reply_text(welcome_text)
logger.info(f"Пользователь {user.id} ({user.username}) запустил бота")


async def help_command(update: Update, context):
help_text = """
🤖 Доступные команды:


/start - Запуск бота
/help - Показать эту справку
/status - Статус бота


Просто отправьте сообщение, и я отвечу!
"""
await update.message.reply_text(help_text)


async def status_command(update: Update, context):
await update.message.reply_text("\u2705 Бот работает нормально!")


async def handle_message(update: Update, context):
user = update.effective_user
message_text = update.message.text
logger.info(f"Сообщение от {user.id} ({user.username}): {message_text}")
if "привет" in message_text.lower():
response = f"Привет, {user.first_name}! 😊"
elif "как дела" in message_text.lower():
response = "У меня всё отлично! А у тебя как?"
elif "спасибо" in message_text.lower():
response = "Пожалуйста! Рад помочь! 😊"
else:
response = f"Получил твоё сообщение: '{message_text}'\nОтправь /help для списка команд."


await update.message.reply_text(response)


# Добавление обработчиков
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
