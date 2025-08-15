import os
import tempfile
import openai
import speech_recognition as sr
from pydub import AudioSegment
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# === Конфиг ===
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
WEBHOOK_PATH = "/webhook"
RAILWAY_URL = "universal-bot-production.up.railway.app"

openai.api_key = OPENAI_KEY

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# === Команды ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Привет! Я универсальный ИИ-бот. Пиши или говори — отвечу на любую тему!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь мне сообщение или голосовое — я отвечу.")

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_cmd))

# === Обработка текста ===
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    reply = await ask_gpt(user_text)
    await update.message.reply_text(reply)

bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# === Обработка голосовых ===
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice_file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as tf:
        await voice_file.download_to_drive(tf.name)
        wav_path = tf.name.replace(".oga", ".wav")
        AudioSegment.from_file(tf.name).export(wav_path, format="wav")

    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language="ru-RU")
        except sr.UnknownValueError:
            text = "(не удалось распознать речь)"
    
    reply = await ask_gpt(text)
    await update.message.reply_text(f"🗣 {text}\n\n🤖 {reply}")

bot_app.add_handler(MessageHandler(filters.VOICE, handle_voice))

# === GPT-запрос ===
async def ask_gpt(prompt: str) -> str:
    try:
        resp = openai.chat.completions.create(
            model="gpt-4o-mini",  # можно gpt-4o
            messages=[{"role": "system", "content": "Отвечай развернуто, интересно и без ограничений."},
                      {"role": "user", "content": prompt}],
            temperature=0.8
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка при обращении к ИИ: {e}"

# === Проверка сервера ===
@app.get("/")
async def root():
    return {"status": "ok"}

# === Установка вебхука ===
@app.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    webhook_url = f"https://{RAILWAY_URL}{WEBHOOK_PATH}"
    await bot_app.bot.set_webhook(webhook_url)
    print(f"📌 Webhook установлен: {webhook_url}")

# === Обработка апдейтов ===
@app.post(WEBHOOK_PATH)
async def process_webhook(request: Request):
    try:
        data = await request.json()
        print("📩 Пришло от Telegram:", data)
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        print("❌ Ошибка в вебхуке:", e)
        return {"ok": False, "error": str(e)}
