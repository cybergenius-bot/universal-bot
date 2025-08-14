import os
import tempfile
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from pydub import AudioSegment
import ffmpeg
from langdetect import detect
from openai import OpenAI

# 🔑 Ключи
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
PAYPAL_LINK = os.getenv("PAYPAL_LINK", "https://www.paypal.com/paypalme/yourlink")  # твоя ссылка PayPal

client = OpenAI(api_key=OPENAI_API_KEY)

# --- FastAPI ---
app = FastAPI()

# --- Telegram ---
application = Application.builder().token(TELEGRAM_TOKEN).build()


# 📌 Мультиязычное приветствие
def get_greeting(lang_code):
    if lang_code.startswith("he"):
        return "שלום! אני בוט אוניברסלי. שלח לי טקסט, קול, תמונה או וידאו."
    elif lang_code.startswith("en"):
        return "Hello! I am a universal bot. Send me text, voice, photo, or video."
    else:
        return "👋 Привет! Я универсальный бот. Отправь мне текст, голос, фото или видео."


# 📌 Команда /start
async def start(update: Update, context):
    lang_code = update.effective_user.language_code or "ru"
    await update.message.reply_text(get_greeting(lang_code))


# 📌 Оплата PayPal
async def buy_premium(update: Update, context):
    keyboard = [[InlineKeyboardButton("💳 Pay with PayPal", url=PAYPAL_LINK)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Чтобы получить полный доступ, оплатите через PayPal:",
        reply_markup=reply_markup
    )


# 📌 Обработка текста
async def handle_text(update: Update, context):
    user_text = update.message.text
    try:
        lang = detect(user_text)
    except:
        lang = "ru"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Ты умный, дружелюбный и даёшь подробные ответы."},
            {"role": "user", "content": user_text}
        ]
    )
    await update.message.reply_text(response.choices[0].message.content)


# 📌 Обработка голосовых
async def handle_voice(update: Update, context):
    file = await context.bot.get_file(update.message.voice.file_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as ogg_file:
        await file.download_to_drive(ogg_file.name)
        audio = AudioSegment.from_file(ogg_file.name, format="ogg")
        wav_path = ogg_file.name.replace(".ogg", ".wav")
        audio.export(wav_path, format="wav")

    with open(wav_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file
        )
    await update.message.reply_text(f"🗣 {transcription.text}")


# 📌 Обработка фото
async def handle_photo(update: Update, context):
    file = await context.bot.get_file(update.message.photo[-1].file_id)
    photo_path = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg").name
    await file.download_to_drive(photo_path)
    await update.message.reply_text("📷 Фото получено. В будущем я смогу анализировать изображения.")


# 📌 Обработка видео
async def handle_video(update: Update, context):
    file = await context.bot.get_file(update.message.video.file_id)
    video_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    await file.download_to_drive(video_path)

    audio_path = video_path.replace(".mp4", ".wav")
    ffmpeg.input(video_path).output(audio_path, format="wav").run()

    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file
        )
    await update.message.reply_text(f"🎬 {transcription.text}")


# --- Вебхук ---
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse(content={"status": "ok"})


# --- Проверка ---
@app.get("/")
async def root():
    return {"status": "ok"}


# --- Хендлеры ---
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("buy", buy_premium))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
application.add_handler(MessageHandler(filters.VOICE, handle_voice))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.VIDEO, handle_video))


# --- Запуск ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
