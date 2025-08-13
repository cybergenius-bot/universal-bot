import os
import asyncio
import logging
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes,
    filters
)

# ---------- ЛОГИ ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s"
)
log = logging.getLogger("universal-bot")

# ---------- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ----------
BOT_TOKEN = os.environ["TELEGRAM_TOKEN"]            # токен бота от @BotFather
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")   # ключ OpenAI
PUBLIC_URL = os.environ["PUBLIC_URL"]               # домен Railway, напр. https://universal-bot-production.up.railway.app

PAYPAL_CLIENT_ID = os.environ["PAYPAL_CLIENT_ID"]
PAYPAL_SECRET    = os.environ["PAYPAL_SECRET"]
PAYPAL_MODE      = os.environ.get("PAYPAL_MODE", "sandbox").lower()  # 'sandbox' или 'live'

# Базовый URL PayPal
PAYPAL_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

# ---------- OpenAI (асинхронный клиент через httpx) ----------
# Используем официальное HTTPS API вручную (просто и без лишних зависимостей).
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"

# ---------- Telegram Application ----------
application: Application = ApplicationBuilder().token(BOT_TOKEN).build()

# ---------- FASTAPI ----------
app = FastAPI(title="Universal Bot")

# --------- ВСПОМОГАТЕЛЬНОЕ: OpenAI ответ ---------
async def ask_openai(prompt: str) -> str:
    if not OPENAI_KEY:
        return "OpenAI ключ не задан. Установите переменную OPENAI_API_KEY."

    headers = {
        "Authorization": f"Bearer {OPENAI_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "Ты умный, вежливый универсальный помощник. Отвечай кратко и по делу."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(OPENAI_CHAT_URL, headers=headers, json=payload)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()

# --------- ВСПОМОГАТЕЛЬНОЕ: PayPal токен ---------
async def paypal_access_token() -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{PAYPAL_BASE}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            data={"grant_type": "client_credentials"},
        )
        r.raise_for_status()
        return r.json()["access_token"]

# --------- Создание PayPal заказа и ссылка на оплату ---------
async def create_paypal_order(amount: str, currency: str, chat_id: int) -> str:
    token = await paypal_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # После оплаты PayPal вернёт пользователя на наши урлы:
    return_url = f"{PUBLIC_URL}/paypal/return?chat_id={chat_id}"
    cancel_url = f"{PUBLIC_URL}/paypal/cancel?chat_id={chat_id}"

    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "amount": {"currency_code": currency, "value": amount}
        }],
        "application_context": {
            "return_url": return_url,
            "cancel_url": cancel_url,
            "shipping_preference": "NO_SHIPPING",
            "user_action": "PAY_NOW"
        }
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{PAYPAL_BASE}/v2/checkout/orders", headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
        approve = next((l["href"] for l in data["links"] if l["rel"] == "approve"), "")
        return approve or "Не удалось получить ссылку на оплату."

# --------- Захват (CAPTURE) заказа после возврата с PayPal ---------
async def capture_paypal_order(order_id: str) -> bool:
    token = await paypal_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture", headers=headers)
        if r.status_code // 100 == 2:
            return True
        log.error("Capture failed: %s %s", r.status_code, r.text)
        return False

# ---------- Telegram handlers ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я универсальный бот.\n"
        "Команды:\n"
        "• /prices — тарифы\n"
        "• /pay3 — оплатить 3$ (разовая)\n"
        "• /pay27 — оплатить 27$ (безлимит месяц)\n\n"
        "Просто задавайте вопросы на любую тему."
    )
    await update.message.reply_text(text)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Спроси что угодно или используй /prices, /pay3, /pay27.")

async def cmd_prices(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Тарифы:\n"
        "• 5 вопросов — бесплатно\n"
        "• Разовый пакет — 3$\n"
        "• Безлимит на месяц — 27$\n"
        "Используй /pay3 или /pay27 для оплаты через PayPal."
    )

async def cmd_pay3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    url = await create_paypal_order("3.00", "USD", chat_id)
    await update.message.reply_text(f"Ссылка на оплату 3$: {url}")

async def cmd_pay27(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    url = await create_paypal_order("27.00", "USD", chat_id)
    await update.message.reply_text(f"Ссылка на оплату 27$: {url}")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    try:
        reply = await ask_openai(user_text)
    except Exception as e:
        log.exception("OpenAI error")
        reply = "Пока не могу ответить, попробуйте ещё раз чуть позже."
    await update.message.reply_text(reply)

# Регистрируем хендлеры
application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(CommandHandler("help", cmd_help))
application.add_handler(CommandHandler("prices", cmd_prices))
application.add_handler(CommandHandler("pay3", cmd_pay3))
application.add_handler(CommandHandler("pay27", cmd_pay27))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

# ---------- FastAPI endpoints ----------

# Точка приёма апдейтов от Telegram (вебхук)
@app.post(f"/tg/{BOT_TOKEN}")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.update_queue.put(update)
    return JSONResponse({"ok": True})

# PayPal вернул пользователя после успешной оплаты
@app.get("/paypal/return")
async def paypal_return(token: str, chat_id: Optional[int] = None):
    # token = это order_id
    ok = await capture_paypal_order(order_id=token)
    if chat_id:
        try:
            if ok:
                await application.bot.send_message(chat_id, "Оплата прошла успешно ✅. Спасибо!")
            else:
                await application.bot.send_message(chat_id, "Не удалось подтвердить оплату ❌.")
        except Exception:
            pass
    return PlainTextResponse("OK")

# Пользователь отменил оплату
@app.get("/paypal/cancel")
async def paypal_cancel(chat_id: Optional[int] = None):
    if chat_id:
        try:
            await application.bot.send_message(chat_id, "Оплата отменена.")
        except Exception:
            pass
    return PlainTextResponse("Canceled")

# ---------- Жизненный цикл FastAPI <-> PTB ----------
@app.on_event("startup")
async def on_startup():
    # Инициализируем и запускаем Telegram-приложение
    await application.initialize()
    await application.start()

    # Ставим вебхук на наш публичный URL
    url = f"{PUBLIC_URL}/tg/{BOT_TOKEN}"
    await application.bot.set_webhook(url=url)
    log.info("Webhook set to %s", url)

@app.on_event("shutdown")
async def on_shutdown():
    # Корректно останавливаем PTB (важно, иначе в логах 'shutdown was never awaited')
    await application.stop()
    await application.shutdown()

    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return JSONResponse({"ok": True})
    log.info("Bot stopped gracefully")
