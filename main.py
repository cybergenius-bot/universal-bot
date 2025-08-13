import os
import base64
from io import BytesIO

from fastapi import FastAPI, Request
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, AIORateLimiter,
    MessageHandler, CommandHandler, filters
)

TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

client = OpenAI(api_key=OPENAI_KEY)

app = FastAPI()
application: Application = (
    ApplicationBuilder()
    .token(TOKEN)
    .rate_limiter(AIORateLimiter())
    .build()
)

# ===== Команды =====

async def start_cmd(update: Update, _):
    await update.message.reply_text(
        "Привет! Я универсальный помощник.\n"
        "Пиши вопросы на любые темы, присылай фото — разберу."
    )

application.add_handler(CommandHandler("start", start_cmd))

# ===== Помощники для ИИ =====

async def ask_openai_text(prompt: str) -> str:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {"role": "system",
             "content": (
                "Ты полезный русскоязычный ассистент. "
                "Отвечай коротко и по делу, давай шаги только если нужно."
             )},
            {"role": "user", "content": prompt}
        ],
    )
    return resp.choices[0].message.content.strip()

async def ask_openai_vision(photo_bytes: bytes, user_prompt: str = "") -> str:
    b64 = base64.b64encode(photo_bytes).decode()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": user_prompt or "Опиши, что на фото, и ответь на вопрос пользователя, если он есть."},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
        }]
    )
    return resp.choices[0].message.content.strip()

# ===== Обработчики сообщений =====

async def on_text(update: Update, _):
    text = (update.message.text or "").strip()
    if not text:
        return
    try:
        reply = await ask_openai_text(text)
    except Exception as e:
        reply = f"Не смог получить ответ ИИ: {e}"
    await update.message.reply_text(reply)

async def on_photo(update: Update, context):
    try:
        # берём самое большое фото
        file_id = update.message.photo[-1].file_id
        file = await context.bot.get_file(file_id)
        buf = await file.download_as_bytearray()
        # подпись пользователя (если есть)
        caption = (update.message.caption or "").strip()
        reply = await ask_openai_vision(bytes(buf), caption)
    except Exception as e:
        reply = f"Не удалось обработать фото: {e}"
    await update.message.reply_text(reply)

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
application.add_handler(MessageHandler(filters.PHOTO, on_photo))

# ===== FastAPI webhook endpoint =====
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.initialize()
    await application.process_update(update)
    return {"ok": True}
