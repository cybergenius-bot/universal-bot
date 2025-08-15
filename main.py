import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application
from openai import OpenAI

# --- Логирование ---
logging.basicConfig(level=logging.INFO)

# --- Переменные окружения ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Инициализация клиентов ---
client_ai = OpenAI(api_key=OPENAI_API_KEY)
application = Application.builder().token(TELEGRAM_TOKEN).build()
app = FastAPI()

@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    """Обработка входящих апдейтов от Telegram."""
    if token != TELEGRAM_TOKEN:
        logging.error("❌ Неверный токен в webhook URL")
        return {"status": "error", "reason": "wrong token"}

    try:
        data = await request.json()
        logging.info(f"📩 Incoming update: {data}")

        update = Update.de_json(data, application.bot)

        if update.message and update.message.text:
            user_message = update.message.text.strip()
            logging.info(f"💬 User said: {user_message}")

            try:
                ai_response = client_ai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": user_message}]
                )
                answer = ai_response.choices[0].message.content.strip()
            except Exception as e:
                logging.exception("🔥 Ошибка при запросе к OpenAI")
                answer = "Произошла ошибка при обработке запроса к ИИ."

            await update.message.reply_text(answer)
        else:
            logging.info("⚠ Сообщение без текста — пропускаем.")

    except Exception as e:
        logging.exception("🔥 Ошибка в webhook обработчике")
        return {"status": "error", "reason": str(e)}

    return {"status": "ok"}

@app.get("/")
async def root():
    return {"status": "Bot is running"}

application.add_handler(
    __import__("telegram.ext").ext.MessageHandler(
        __import__("telegram.ext").ext.filters.TEXT & ~__import__("telegram.ext").ext.filters.COMMAND,
        message_handler
    )
)
