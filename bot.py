import os
import logging
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SYSTEM_PROMPT = (
    "Ты — мощный AI-ассистент GPT‑4.0..."
)

if not TELEGRAM_TOKEN or not os.getenv("OPENAI_API_KEY"):
    logger.error("TELEGRAM_TOKEN или OPENAI_API_KEY не заданы")
    exit(1)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_tokens=2048,
            temperature=0.7
        )
        reply = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Ошибка GPT‑4.0: %s", e)
        reply = "Произошла ошибка при обращении к GPT‑4.0."

    await update.message.reply_text(reply)
