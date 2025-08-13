import os
import io
import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- OpenAI (>=1.0) ---
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

# --- PayPal Checkout SDK ---
try:
    from paypalcheckoutsdk.core import PayPalHttpClient, SandboxEnvironment, LiveEnvironment
    from paypalcheckoutsdk.orders import OrdersCreateRequest
    PAYPAL_AVAILABLE = True
except Exception:
    PAYPAL_AVAILABLE = False

# ----------------- ENV -----------------
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN", "")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
RAILWAY_URL     = os.getenv("RAILWAY_URL", "").rstrip("/")
PORT            = int(os.getenv("PORT", "8080"))

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET    = os.getenv("PAYPAL_SECRET", "")
PAYPAL_MODE      = (os.getenv("PAYPAL_MODE", "sandbox") or "sandbox").lower()  # 'sandbox' | 'live'

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is not set")
if not RAILWAY_URL or not RAILWAY_URL.startswith("http"):
    raise RuntimeError(f"RAILWAY_URL is not set (current: {RAILWAY_URL})")

# ----------------- LOGS -----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s: %(message)s"
)
log = logging.getLogger("universal-bot")

# ----------------- OpenAI client -----------------
oa_client: Optional["OpenAI"] = None
if OPENAI_AVAILABLE and OPENAI_API_KEY:
    oa_client = OpenAI(api_key=OPENAI_API_KEY)
else:
    log.warning("OpenAI client not configured (no library or OPENAI_API_KEY). Text answers will be simple.")

# ----------------- PayPal client -----------------
pp_client: Optional["PayPalHttpClient"] = None
if PAYPAL_AVAILABLE and PAYPAL_CLIENT_ID and PAYPAL_SECRET:
    if PAYPAL_MODE == "live":
        env = LiveEnvironment(client_id=PAYPAL_CLIENT_ID, client_secret=PAYPAL_SECRET)
    else:
        env = SandboxEnvironment(client_id=PAYPAL_CLIENT_ID, client_secret=PAYPAL_SECRET)
    pp_client = PayPalHttpClient(env)
else:
    log.warning("PayPal not configured (no SDK or credentials). /buy will be disabled.")

# ----------------- Telegram Application -----------------
application = Application.builder().token(TELEGRAM_TOKEN).build()

# ---------- Handlers ----------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я универсальный бот.\n"
        "• напиши вопрос — отвечу с помощью ИИ\n"
        "• пришли голосовое — расшифрую и отвечу\n"
        "• пришли фото/видео/файл — подтвержу получение\n"
        "• /buy — ссылка на оплату PayPal\n"
        "Работаю 24/7 на Railway."
    )
    await update.effective_message.reply_text(text)

async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not pp_client:
        await update.effective_message.reply_text("Оплата временно недоступна: не настроен PayPal.")
        return

    # Демо-заказ на 3.00 USD
    order = OrdersCreateRequest()
    order.prefer("return=representation")
    order.request_body({
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {"currency_code": "USD", "value": "3.00"},
            "description": "Доступ к боту (демо)"
        }],
        # Страницы возврата можно заменить на ваш сайт/лендинг
        "application_context": {
            "brand_name": "UniversalBot",
            "landing_page": "LOGIN",
            "user_action": "PAY_NOW",
            "return_url": f"{RAILWAY_URL}/paypal/success",
            "cancel_url": f"{RAILWAY_URL}/paypal/cancel"
        }
    })
    try:
        resp = pp_client.execute(order)
        approval = next((l.href for l in resp.result.links if l.rel == "approve"), None)
        if approval:
            await update.effective_message.reply_text(f"Ссылка для оплаты (PayPal): {approval}")
        else:
            await update.effective_message.reply_text("Не удалось получить ссылку на оплату.")
    except Exception as e:
        log.exception("PayPal order error")
        await update.effective_message.reply_text(f"Ошибка PayPal: {e}")

async def text_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = (update.message.text or "").strip()

    # если OpenAI доступен — делаем интеллектуальный ответ
    if oa_client:
        try:
            completion = oa_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role":"system","content":"Ты дружелюбный ассистент телеграм-бота. Отвечай кратко и по делу, на русском."},
                    {"role":"user","content": user_text}
                ],
                temperature=0.5,
                max_tokens=400
            )
            answer = completion.choices[0].message.content.strip()
            await update.effective_message.reply_text(answer)
            return
        except Exception:
            log.exception("OpenAI error")
            # если ИИ упал — запасной простой ответ
    # fallback
    await update.effective_message.reply_text(f"Вы спросили: «{user_text}». Получено!")

async def voice_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расшифровка голосовых через OpenAI Whisper"""
    if not oa_client:
        await update.effective_message.reply_text("Расшифровка недоступна: не настроен OpenAI.")
        return

    file = await context.bot.get_file(update.message.voice.file_id)
    bio = io.BytesIO()
    await file.download_to_memory(bio)
    bio.seek(0)

    try:
        tr = oa_client.audio.transcriptions.create(
            model="whisper-1",
            file=("voice.ogg", bio, "audio/ogg")
        )
        text = tr.text.strip()
        await update.effective_message.reply_text(f"Вы сказали: {text}")
        # сразу отправим ответ ИИ на расшифровку
        completion = oa_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role":"system","content":"Ты помощник-эксперт. Отвечай кратко и полезно."},
                {"role":"user","content": text}
            ],
            temperature=0.5,
            max_tokens=300
        )
        answer = completion.choices[0].message.content.strip()
        await update.effective_message.reply_text(answer)
    except Exception:
        log.exception("Whisper error")
        await update.effective_message.reply_text("Не удалось распознать голосовое.")

async def photo_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.photo[-1].file_id)
    await update.effective_message.reply_text("Фото получил 👍 (анализ по картинкам подключим позже).")

async def video_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.video.file_id)
    await update.effective_message.reply_text("Видео получил 👍 (обработку видео добавим позже).")

async def doc_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await context.bot.get_file(update.message.document.file_id)
    await update.effective_message.reply_text("Файл получил 👍")

# регистрация хендлеров
application.add_handler(CommandHandler("start", start_cmd))
application.add_handler(CommandHandler("buy", buy_cmd))
application.add_handler(MessageHandler(filters.VOICE, voice_msg))
application.add_handler(MessageHandler(filters.PHOTO, photo_msg))
application.add_handler(MessageHandler(filters.VIDEO, video_msg))
application.add_handler(MessageHandler(filters.Document.ALL, doc_msg))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_msg))

# ----------------- FastAPI + webhook -----------------
app = FastAPI()

WEBHOOK_PATH = f"/webhook/{TELEGRAM_TOKEN}"

@app.on_event("startup")
async def on_startup():
    # ставим вебхук
    url = f"{RAILWAY_URL}{WEBHOOK_PATH}"
    log.info(f"Setting webhook to {url}")
    await application.bot.set_webhook(url)
    # запускаем обработчик приложения (без .run_polling())
    await application.initialize()
    await application.start()

@app.on_event("shutdown")
async def on_shutdown():
    try:
        await application.stop()
        await application.shutdown()
    except Exception:
        pass

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})

@app.get("/")
def health():
    return {"ok": True, "service": "universal-bot"}

@app.get("/paypal/success")
def paypal_success():
    return PlainTextResponse("Оплата успешно выполнена. Спасибо!")

@app.get("/paypal/cancel")
def paypal_cancel():
    return PlainTextResponse("Оплата отменена. Вы можете попробовать снова командой /buy.")

# локальный запуск (на Railway uvicorn запускается по Procfile)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
