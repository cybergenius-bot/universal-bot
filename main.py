import os
import io
import asyncio
from typing import List

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from telegram import Update, InputFile
from telegram.ext import Application, ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

# ===== OpenAI (официальный SDK v1.x) =====
from openai import OpenAI
openai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# ===== Конфиг через переменные окружения (Railway -> Variables) =====
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
RAILWAY_URL   = os.environ.get("RAILWAY_URL")  # https://universal-bot-production.up.railway.app
WEBHOOK_PATH  = "/webhook"
WEBHOOK_URL   = os.environ.get("WEBHOOK_URL", (RAILWAY_URL.rstrip("/") + WEBHOOK_PATH) if RAILWAY_URL else None)

# ===== Универсальный стиль ответов (подлиннее и полезнее) =====
SYSTEM_PROMPT = (
    "Ты — универсальный помощник. Отвечай развёрнуто, по пунктам, давай практические шаги, примеры и предупреждения. "
    "Если у пользователя картинка или фотография с задачей — сначала коротко опиши, что видишь, затем реши задачу. "
    "Если пришёл голос/видео — сначала распознай речь, потом дай полный ответ по сути запроса. "
    "Пиши по-русски, если пользователь пишет по-русски."
)

# ===== FastAPI =====
app = FastAPI()

# Для PTB нам нужен Application как singleton
tg_app: Application | None = None


# ---------- Обработчики команд ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я универсальный бот. Отправь текст, фото с задачей, голосовое или видео — разберу и отвечу развёрнуто."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Могу: \n"
        "• Текст — подробные ответы\n"
        "• Фото — опишу и решу задачу с изображения\n"
        "• Голос/Видео — распознаю и отвечу по сути\n"
        "• Работаю по вебхуку 24/7 на Railway\n"
        "Попробуй отправить фото уравнения или голосовой вопрос."
    )


# ---------- ТЕКСТ ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_text},
        ],
        temperature=0.4,
        max_tokens=800,
    )

    answer = completion.choices[0].message.content
    await update.message.reply_text(answer)


# ---------- ФОТО (анализ + решение задач со снимка) ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Берём самый большой размер
    photo = update.message.photo[-1]
    file  = await photo.get_file()
    file_bytes = await file.download_as_bytearray()

    # Отправляем как image_url = data URI (OpenAI vision понимает base64? – проще отправить как "image[]": bytes)
    # В SDK v1 можно дать binary через "image[]", но для chat-vision удобнее указать type=image_url с data: URI.
    import base64
    b64 = base64.b64encode(bytes(file_bytes)).decode("utf-8")
    data_uri = f"data:image/jpeg;base64,{b64}"

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Проанализируй фото. Если на нём задача/уравнение — реши по шагам."},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ],
            },
        ],
        temperature=0.3,
        max_tokens=900,
    )
    answer = completion.choices[0].message.content
    await update.message.reply_text(answer or "Готово.")


# ---------- ГОЛОС (распознаём + отвечаем) ----------
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    file  = await voice.get_file()
    data  = await file.download_as_bytearray()  # .ogg (opus) — Whisper принимает ogg/mp3/mp4/wav

    # Распознаём в OpenAI Whisper
    transcript = openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=io.BytesIO(bytes(data)),  # bytes-like
        # без указания mime: OpenAI определит сам
    )
    user_text = (transcript.text or "").strip() or "Не удалось распознать речь."

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Это вопрос из голосового сообщения: {user_text}"},
        ],
        temperature=0.4,
        max_tokens=800,
    )
    answer = completion.choices[0].message.content
    await update.message.reply_text(f"Распознал: {user_text}\n\nОтвет:\n{answer}")


# ---------- ВИДЕО (распознаём аудиодорожку + отвечаем) ----------
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    file  = await video.get_file()
    data  = await file.download_as_bytearray()  # mp4 — Whisper тоже принимает

    transcript = openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=io.BytesIO(bytes(data)),
    )
    spoken = (transcript.text or "").strip() or "Речь не распознана."

    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Видео содержит такую речь: {spoken}\nДай полный ответ/решение по теме."},
        ],
        temperature=0.4,
        max_tokens=900,
    )
    answer = completion.choices[0].message.content
    await update.message.reply_text(f"Из видео распознал: {spoken}\n\nОтвет:\n{answer}")


# ---------- Сборка Telegram Application ----------
def build_telegram_app() -> Application:
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .concurrent_updates(True)   # без гонок, устойчивее на вебхуке
        .build()
    )

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help",  cmd_help))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO,  handle_photo))
    application.add_handler(MessageHandler(filters.VOICE,  handle_voice))
    application.add_handler(MessageHandler(filters.VIDEO,  handle_video))

    return application


# ---------- Вебхук: Telegram -> FastAPI ----------
class TGUpdate(BaseModel):
    update_id: int


@app.on_event("startup")
async def on_startup():
    global tg_app
    if tg_app is None:
        tg_app = build_telegram_app()

    # Устанавливаем вебхук только если есть адрес
    if WEBHOOK_URL:
        # Важно: очищаем старые и ставим новый вебхук (без event loop ошибок)
        bot = tg_app.bot
        await bot.delete_webhook(drop_pending_updates=False)
        await bot.set_webhook(url=WEBHOOK_URL, allowed_updates=["message"])
    else:
        print("WARNING: WEBHOOK_URL/RAILWAY_URL не задан — вебхук не будет установлен.")


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Точка входа для Telegram."""
    if tg_app is None:
        return JSONResponse({"ok": False, "error": "app not ready"}, status_code=503)

    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return JSONResponse({"ok": True})


@app.get("/")
async def root():
    return {"status": "ok", "service": "universal-bot"}


# Локальный запуск (Railway использует свой entrypoint, но это не мешает)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
    await application.process_update(update)
    return JSONResponse({"ok": True})

@api.get("/")
def health():
    return PlainTextResponse("universal-bot: OK")
