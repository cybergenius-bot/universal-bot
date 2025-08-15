import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, MessageHandler, filters
from openai import OpenAI

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Переменные окружения ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("❌ Не заданы TELEGRAM_TOKEN или OPENAI_API_KEY в переменных окружения")

# --- Инициализация клиентов ---
client_ai = OpenAI(api_key=OPENAI_API_KEY)
application = Application.builder().token(TELEGRAM_TOKEN).build()
app = FastAPI()

# --- Обработчик сообщений ---
async def handle_message(update: Update, context):
    if update.message and update.message.text:
        user_message = update.message.text.strip()
        logging.info(f"💬 User: {user_message}")

        try:
            ai_response = client_ai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": user_message}]
            )
            answer = ai_response.choices[0].message.content.strip()
        except Exception as e:
            logging.exception("🔥 Ошибка запроса к OpenAI")
            answer = "Произошла ошибка при обработке вашего сообщения."

        await update.message.reply_text(answer)

# Добавляем обработчик для всех текстовых сообщений
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# --- Webhook ---
@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TELEGRAM_TOKEN:
        return {"status": "error", "reason": "wrong token"}

    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "Bot is running"}
