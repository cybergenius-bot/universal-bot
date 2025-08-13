import os
import asyncio
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, MessageHandler, filters

# ========= Конфигурация =========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
PORT = int(os.environ.get("PORT", "8000"))  # Railway/Render выставляет PORT

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN env var is missing")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY env var is missing")

client = OpenAI(api_key=OPENAI_API_KEY)

# ========= Логика OpenAI =========
async def ask_openai_text(user_text: str) -> str:
    # Мини‑система: делаем бота универсальным ассистентом
    system_prompt = (
        "Ты — универсальный помощник Telegram. Отвечай кратко и по делу; "
        "умей объяснять, давать примеры, форматировать списки."
    )
    resp = await asyncio.to_thread(
        lambda: client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.6,
            max_tokens=500,
        )
    )
    return resp.choices[0].message.content.strip()

# ========= Хэндлеры TG =========
async def cmd_start(update: Update, _):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Спроси о чем угодно 🙂"
    )

async def on_text(update: Update, _):
    text = (update.message.text or "").strip()
    if not text:
        return
    try:
        reply = await ask_openai_text(text)
    except Exception as e:
        reply = f"Не смог получить ответ ИИ: {e}"
    await update.message.reply_text(reply)

# ========= Приложение PTB + FastAPI (webhook) =========
app = FastAPI()
application: Optional[Application] = None

async def build_app() -> Application:
    global application
    if application:
        return application
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .build()
    )
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return application

@app.on_event("startup")
async def on_startup():
    # Стартуем PTB внутри FastAPI
    app_ptb = await build_app()
    # PTB 20.x: запускаем в фоне
    asyncio.create_task(app_ptb.initialize())
    asyncio.create_task(app_ptb.start())

@app.on_event("shutdown")
async def on_shutdown():
    if application:
        await application.stop()
        await application.shutdown()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Маршрут для Telegram webhook"""
    data = await request.json()
    app_ptb = await build_app()
    try:
        update = Update.de_json(data, app_ptb.bot)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    await app_ptb.process_update(update)
    return {"ok": True}

# Для локального запуска (не используется на Railway, но пусть будет)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
