import os
import base64
import io

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI

# ====== ENV ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # именно такое имя переменной в Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
RAILWAY_URL = os.getenv("RAILWAY_URL")  # вида https://universal-bot-production.up.railway.app

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set in environment")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set in environment")

# ====== Clients ======
client = OpenAI(api_key=OPENAI_API_KEY)
application = Application.builder().token(TELEGRAM_TOKEN).build()
app = FastAPI()


# ====== Handlers ======
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот.\n"
        "Отправь текст, фото или голосовое — отвечу.\n"
        "Работаю по вебхуку 24/7 на Railway."
    )


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text or ""
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",
             "content": "Отвечай развёрнуто и по делу. Если просят список — давай структурировано."},
            {"role": "user", "content": user_text},
        ],
        temperature=0.4,
    )
    await update.message.reply_text(resp.choices[0].message.content.strip())


async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        return
    # Берём самую большую фотографию
    photo = update.message.photo[-1]
    tg_file = await ctx.bot.get_file(photo.file_id)
    # Скачиваем байты
    b = await tg_file.download_as_bytearray()
    b64 = base64.b64encode(b).decode("utf-8")

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",
             "content": "Ты — ассистент‑визион: опиши изображение и ответь на вопрос пользователя, если он есть."},
            {
                "role": "user",
                "content": [
                    {"type": "input_text",
                     "text": update.message.caption or "Опиши картинку и сделай выводы, если они уместны."},
                    {"type": "input_image",
                     "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
                ],
            },
        ],
    )
    await update.message.reply_text(resp.choices[0].message.content.strip())


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not update.message.voice:
        return
    voice = update.message.voice
    tg_file = await ctx.bot.get_file(voice.file_id)
    ogg_bytes = await tg_file.download_as_bytearray()

    # Передаём .ogg напрямую в OpenAI (без ffmpeg/pydub)
    file_tuple = ("voice.ogg", io.BytesIO(ogg_bytes), "audio/ogg")
    tr = client.audio.transcriptions.create(
        model="gpt-4o-mini-transcribe",
        file=file_tuple,
        response_format="verbose_json",
    )
    text = tr.text.strip() if hasattr(tr, "text") else str(tr)

    # Отвечаем содержательно на то, что сказали голосом
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",
             "content": "Отвечай развёрнуто и дружелюбно"},
            {"role": "user", "content": f"Пользователь сказал голосом: «{text}». Дай полезный ответ."},
        ],
        temperature=0.5,
    )
    await update.message.reply_text(resp.choices[0].message.content.strip())


# ====== Telegram webhook endpoint ======
@app.post("/webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}


# ====== FastAPI lifecycle ======
@app.on_event("startup")
async def on_startup():
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))

    # Ставим вебхук (если указан URL)
    if RAILWAY_URL:
        await application.bot.set_webhook(url=f"{RAILWAY_URL}/webhook")


# Локальный запуск (polling) — на Railway это не используется
if __name__ == "__main__":
    application.run_polling()
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    update = Update.de_json(data, app_tg.bot)
    await app_tg.process_update(update)
    return {"ok": True}
