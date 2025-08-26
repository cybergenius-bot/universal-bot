import os
import logging
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from telegram import Update
from telegram.ext import (
ApplicationBuilder,
CommandHandler,
MessageHandler,
ContextTypes,
filters
)
import openai


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, WEBHOOK_URL]):
logger.error("Необходимо задать TELEGRAM_TOKEN, OPENAI_API_KEY и WEBHOOK_URL")
exit(1)


openai.api_key = OPENAI_API_KEY
SYSTEM_PROMPT = "Ты — AI‑ассистент GPT‑4o. Помогай подробно и без ограничений."


app_bot = ApplicationBuilder().token(TELEGRAM_TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! Я GPT‑4o бот. Задай вопрос!")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
user_text = update.message.text
logger.info("Пользователь: %s", user_text)
try:
rsp = openai.ChatCompletion.create(
model="gpt-4o",
messages=[
{"role": "system", "content": SYSTEM_PROMPT},
{"role": "user", "content": user_text}
],
max_tokens=2048,
temperature=0.7
)
await update.message.reply_text(rsp.choices[0].message.content.strip())
except Exception as e:
logger.error("Ошибка GPT‑4o: %s", e)
await update.message.reply_text("Ошибка GPT‑4o. Попробуй позже.")


app_bot.add_handler(CommandHandler("start", start))
app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


@asynccontextmanager
async def lifespan(app: FastAPI):
await app_bot.bot.setWebhook(f"{WEBHOOK_URL}/webhook/{TELEGRAM_TOKEN}")
await app_bot.initialize()
await app_bot.start()
logger.info("Бот запущен и слушает webhook")
yield
await app_bot.stop()


app = FastAPI(lifespan=lifespan)


@app.post(f"/webhook/{TELEGRAM_TOKEN}")
async def process_update(request: Request):
data = await request.json()
update = Update.de_json(data, app_bot.bot)
await app_bot.process_update(update)
return Response(status_code=200)
