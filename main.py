import os
import io
import base64
import logging
import tempfile
import asyncio
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

from telegram import Update, InputFile, MessageEntity
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

from openai import OpenAI
import requests
from PIL import Image
import ffmpeg

# ---------- ЛОГИ ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("universal-bot")

# ---------- ENV ----------
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
RAILWAY_URL    = os.environ["RAILWAY_URL"].rstrip("/")  # напр. https://universal-bot-production.up.railway.app

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET    = os.getenv("PAYPAL_SECRET", os.getenv("PATPAL_SECRET", ""))
PAYPAL_MODE      = os.getenv("PAYPAL_MODE", "sandbox").lower()  # sandbox | live

ANSWER_STYLE = os.getenv("ANSWER_STYLE", "expanded")  # expanded | concise
MAX_TOKENS   = 1500 if ANSWER_STYLE == "expanded" else 600

# ---------- OpenAI ----------
oa = OpenAI(api_key=OPENAI_API_KEY)
TEXT_MODEL   = "gpt-4o-mini"
VISION_MODEL = "gpt-4o-mini"
TTS_MODEL    = "gpt-4o-mini-tts"   # для голосового ответа бота

SYSTEM_PROMPT = (
    "Ты экспертный универсальный ассистент. Отвечай полно и структурировано: "
    "1) краткое резюме, 2) пошаговое объяснение/решение, 3) примеры или чек‑лист, 4) итог. "
    "Если вопрос пришёл с фото/голоса/видео — сначала распознай данные, затем реши задачу. "
    "Избегай воды и пустых фраз."
)
VISION_PROMPT = (
    "Проанализируй изображение. 1) Извлеки текст/формулы (если есть). "
    "2) Объясни, что изображено. 3) Если это задача — реши по шагам. 4) Дай итог."
)

# ---------- Telegram Application ----------
application: Optional[Application] = None

# ---------- FastAPI ----------
api = FastAPI(title="universal-bot")

# ---------- Утилиты ----------
async def send_long(message, text: str):
    """Отправка длинных ответов (Telegram ~4096 символов)."""
    s = (text or "").strip()
    if not s:
        return
    limit = 3900
    while len(s) > limit:
        cut = s.rfind("\n\n", 0, limit)
        if cut == -1:
            cut = s.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        await message.reply_text(s[:cut])
        s = s[cut:]
    await message.reply_text(s)

def tg_file_url(file_path: str) -> str:
    return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"

def pil_to_b64(pil_img: Image.Image) -> str:
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

# ---------- OpenAI вызовы ----------
async def ai_answer_text(prompt: str) -> str:
    def _call():
        resp = oa.chat.completions.create(
            model=TEXT_MODEL,
            temperature=0.35 if ANSWER_STYLE == "expanded" else 0.2,
            max_tokens=MAX_TOKENS,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Сформируй развёрнутый ответ.\nВопрос: {prompt}"},
            ],
        )
        return resp.choices[0].message.content.strip()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _call)

async def ai_answer_image_by_url(image_url: str, question: str = "") -> str:
    def _call():
        resp = oa.chat.completions.create(
            model=VISION_MODEL,
            temperature=0.25,
            max_tokens=MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": VISION_PROMPT + (f"\nВопрос: {question}" if question else "")},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]
            }],
        )
        return resp.choices[0].message.content.strip()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _call)

async def ai_transcribe_ogg(ogg_bytes: bytes) -> str:
    """Whisper понимает .ogg напрямую — без ffmpeg/pydub."""
    wav = io.BytesIO(ogg_bytes)  # можно передать ogg как есть
    wav.name = "audio.ogg"
    tr = oa.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.ogg", wav, "audio/ogg"),
        response_format="text"
    )
    return tr.strip()

async def ai_tts_to_ogg(text: str) -> io.BytesIO:
    """TTS → ogg(voice) для Telegram."""
    speech = oa.audio.speech.create(
        model=TTS_MODEL,
        voice="alloy",
        input=text[:1000]  # не переборщить с длиной
    )
    ogg_bytes = speech.read()
    bio = io.BytesIO(ogg_bytes)
    bio.name = "voice.ogg"
    bio.seek(0)
    return bio

# ---------- PayPal (минимальный checkout) ----------
def _pp_base():
    return "https://api-m.paypal.com" if PAYPAL_MODE == "live" else "https://api-m.sandbox.paypal.com"

def _pp_access_token() -> str:
    r = requests.post(
        f"{_pp_base()}/v1/oauth2/token",
        data={"grant_type": "client_credentials"},
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        timeout=20
    )
    r.raise_for_status()
    return r.json()["access_token"]

def paypal_create_order(amount="3.00", currency="USD"):
    token = _pp_access_token()
    r = requests.post(
        f"{_pp_base()}/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": currency, "value": amount}}],
            "application_context": {
                "brand_name": "UniversalBot",
                "user_action": "PAY_NOW",
                "return_url": f"{RAILWAY_URL}/paypal/return",
                "cancel_url": f"{RAILWAY_URL}/paypal/cancel",
            },
        },
        timeout=20
    )
    r.raise_for_status()
    data = r.json()
    approve = next((l["href"] for l in data["links"] if l["rel"] == "approve"), None)
    return data.get("id"), approve

# ---------- Handlers ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Привет! Я универсальный бот 🤖\n"
        "• Текст — дам развёрнутый ответ\n"
        "• Фото — распознаю и решу, если задача\n"
        "• Голос — распознаю и отвечу, могу ответить голосом (/voice_on)\n"
        "• Видео — извлеку звук и отвечу по содержанию\n"
        "• /buy — оплата PayPal (демо $3)\n"
        "Работаю 24/7."
    )

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        order_id, url = paypal_create_order("3.00", "USD")
        if url:
            await update.effective_message.reply_text(f"Оплатить (PayPal): {url}\nOrder: {order_id}")
        else:
            await update.effective_message.reply_text("Не удалось получить ссылку PayPal.")
    except Exception as e:
        log.exception("PayPal error")
        await update.effective_message.reply_text(f"PayPal: {e}")

async def cmd_voice_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    flag = update.effective_message.text.endswith("_on")
    context.chat_data["voice_mode"] = flag
    await update.effective_message.reply_text("Режим голосового ответа: " + ("ВКЛ" if flag else "ВЫКЛ"))

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    # если в тексте есть URL картинки — тоже поддержим
    url = None
    if update.effective_message.entities:
        for e in update.effective_message.entities:
            if e.type == MessageEntity.URL:
                url = text[e.offset: e.offset + e.length]
                break
    if url:
        ans = await ai_answer_image_by_url(url, f"Проанализируй изображение по ссылке: {url}")
    else:
        ans = await ai_answer_text(text)
    await send_long(update.effective_message, ans)
    if context.chat_data.get("voice_mode"):
        try:
            ogg = await ai_tts_to_ogg(ans)
            await update.effective_message.reply_voice(voice=InputFile(ogg))
        except Exception as e:
            log.warning("TTS failed: %s", e)

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.effective_message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    url = tg_file_url(file.file_path)
    caption = (update.effective_message.caption or "").strip()
    ans = await ai_answer_image_by_url(url, caption)
    await send_long(update.effective_message, ans)
    if context.chat_data.get("voice_mode"):
        try:
            ogg = await ai_tts_to_ogg(ans)
            await update.effective_message.reply_voice(voice=InputFile(ogg))
        except Exception as e:
            log.warning("TTS failed: %s", e)

async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    v = update.effective_message.voice
    file = await context.bot.get_file(v.file_id)
    ogg_bytes = requests.get(tg_file_url(file.file_path), timeout=60).content
    text = await ai_transcribe_ogg(ogg_bytes)
    ans = await ai_answer_text(text)
    await send_long(update.effective_message, f"🗣 Распознал: {text}\n\n{ans}")
    if context.chat_data.get("voice_mode"):
        try:
            ogg = await ai_tts_to_ogg(ans)
            await update.effective_message.reply_voice(voice=InputFile(ogg))
        except Exception as e:
            log.warning("TTS failed: %s", e)

async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Минимум: вытаскиваем аудио, распознаём, отвечаем по содержанию речи."""
    v = update.effective_message.video
    file = await context.bot.get_file(v.file_id)
    mp4_bytes = requests.get(tg_file_url(file.file_path), timeout=120).content

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as fmp4:
        fmp4.write(mp4_bytes); fmp4.flush()
        mp4_path = fmp4.name
    wav_path = mp4_path.replace(".mp4", ".wav")

    try:
        (
            ffmpeg
            .input(mp4_path)
            .output(wav_path, ac=1, ar=16000, format="wav")
            .overwrite_output()
            .run(quiet=True)
        )
        with open(wav_path, "rb") as wavf:
            tr = oa.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", wavf, "audio/wav"),
                response_format="text"
            )
        text = tr.strip()
        ans = await ai_answer_text(f"Видео (аудиосодержание): {text}")
        await send_long(update.effective_message, ans)
        if context.chat_data.get("voice_mode"):
            try:
                ogg = await ai_tts_to_ogg(ans)
                await update.effective_message.reply_voice(voice=InputFile(ogg))
            except Exception as e:
                log.warning("TTS failed: %s", e)
    finally:
        for p in (mp4_path, wav_path):
            try: os.remove(p)
            except Exception: pass

# ---------- Регистрация ----------
def register_handlers(app: Application):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("buy",   cmd_buy))
    app.add_handler(CommandHandler("voice_on",  cmd_voice_mode))
    app.add_handler(CommandHandler("voice_off", cmd_voice_mode))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.VIDEO, on_video))

# ---------- Webhook / lifecycle ----------
WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"
WEBHOOK_URL  = f"{RAILWAY_URL}{WEBHOOK_PATH}"

@api.on_event("startup")
async def on_startup():
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    register_handlers(application)
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(url=WEBHOOK_URL, drop_pending_updates=True)
    log.info(f"Webhook set to {WEBHOOK_URL}")

@api.on_event("shutdown")
async def on_shutdown():
    global application
    if application:
        try:
            await application.bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass
        await application.stop()
        await application.shutdown()
        log.info("Bot stopped")

@api.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    global application
    if not application:
        raise HTTPException(status_code=503, detail="bot not ready")
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})

@api.get("/")
def health():
    return PlainTextResponse("universal-bot: OK")
