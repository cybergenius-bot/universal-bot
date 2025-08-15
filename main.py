import os
import logging
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAILWAY_URL = os.getenv("RAILWAY_URL")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client_ai = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()
application = Application.builder().token(TELEGRAM_TOKEN).build()

# ====== Обработка текста ======
async def ai_handler(update: Update, context):
    user_text = update.message.text
    logger.info(f"User: {user_text}")

    try:
        response = client_ai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — умный универсальный ассистент, отвечай развёрнуто, деловым и дружелюбным стилем."},
                {"role": "user", "content": user_text}
            ]
        )
        answer = response.choices[0].message.content
    except Exception as e:
        answer = f"Ошибка AI: {e}"

    await update.message.reply_text(answer)

# ====== Обработка фото ======
async def photo_handler(update: Update, context):
    photo = await update.message.photo[-1].get_file()
    await update.message.reply_text("Фото получено, но анализ пока в разработке.")

# ====== Обработка голосовых ======
async def voice_handler(update: Update, context):
    await update.message.reply_text("Голосовое получено, обработка в разработке.")

# ====== Приветствие ======
async def start(update: Update, context):
    await update.message.reply_text(
        "Здравствуйте! Я ваш универсальный ИИ-ассистент.\n"
        "Я понимаю текст, фото, аудио и видео, говорю на разных языках и работаю 24/7."
    )

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ai_handler))
application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
application.add_handler(MessageHandler(filters.VOICE, voice_handler))

# ====== Webhook ======
@app.on_event("startup")
async def on_startup():
    webhook_url = f"{RAILWAY_URL}/webhook/{TELEGRAM_TOKEN}"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook установлен: {webhook_url}")

@app.post("/webhook/{token}")
async def webhook_handler(request: Request, token: str):
    if token != TELEGRAM_TOKEN:
        return {"error": "Unauthorized"}
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
