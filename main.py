import os
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI
import aiohttp
import tempfile

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Конфиги ===
BOT_TOKEN = os.getenv("BOT_TOKEN", "8091774335:AAFTHo_xWA0kpAV_CK4BdyWMq2K3Sbg_GaQ")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-proj-...")  # твой ключ
WEBHOOK_URL = f"https://universal-bot-production.up.railway.app/webhook/{BOT_TOKEN}"

client = OpenAI(api_key=OPENAI_API_KEY)

# === FastAPI ===
app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()


# === Приветствие ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Здравствуйте! Я ваш интеллектуальный помощник.\n"
        "Отвечаю на вопросы, анализирую фото, видео и голосовые сообщения.\n"
        "Опишите, что вам нужно, и я помогу."
    )
    await update.message.reply_text(text)


# === Обработка текста ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — профессиональный ассистент без ограничений."},
                {"role": "user", "content": user_text}
            ],
            temperature=0.7
        )
        await update.message.reply_text(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Ошибка GPT: {e}")
        await update.message.reply_text("Произошла ошибка при обработке запроса.")


# === Обработка фото ===
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo = await update.message.photo[-1].get_file()
        file_path = tempfile.mktemp(suffix=".jpg")
        await photo.download_to_drive(file_path)

        # Пример анализа изображения
        with open(file_path, "rb") as f:
            img_response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "Опиши изображение детально."},
                    {"role": "user", "content": "Что изображено на фото?"}
                ]
            )
        await update.message.reply_text(img_response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await update.message.reply_text("Не удалось обработать фото.")


# === Обработка голоса ===
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        voice = await update.message.voice.get_file()
        file_path = tempfile.mktemp(suffix=".ogg")
        await voice.download_to_drive(file_path)

        with open(file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=audio_file
            )

        await handle_text(
            update=update,
            context=context
        )
    except Exception as e:
        logger.error(f"Ошибка обработки голоса: {e}")
        await update.message.reply_text("Не удалось обработать голосовое сообщение.")


# === Роуты FastAPI ===
@app.on_event("startup")
async def startup():
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")


@app.post("/webhook/{token}")
async def webhook_handler(token: str, request: Request):
    if token != BOT_TOKEN:
        return JSONResponse(status_code=403, content={"error": "Неверный токен"})
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.initialize()
    await application.process_update(update)
    return JSONResponse(status_code=200, content={"ok": True})


# === Handlers ===
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))
