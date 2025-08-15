import os
from fastapi import FastAPI, Request
from openai import OpenAI
from telegram import Update
from telegram.ext import Application

TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Создаём клиента OpenAI без proxies
client_ai = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()
application = Application.builder().token(TOKEN).build()

@app.post(f"/webhook/{TOKEN}")
async def webhook(request: Request):
    update = Update.de_json(await request.json(), application.bot)
    await application.process_update(update)
    return {"status": "ok"}

async def ai_answer(text):
    response = client_ai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}]
    )
    return response.choices[0].message.content

async def message_handler(update: Update, context):
    user_text = update.message.text
    answer = await ai_answer(user_text)
    await update.message.reply_text(answer)

application.add_handler(
    __import__("telegram.ext").ext.MessageHandler(
        __import__("telegram.ext").ext.filters.TEXT & ~__import__("telegram.ext").ext.filters.COMMAND,
        message_handler
    )
)
