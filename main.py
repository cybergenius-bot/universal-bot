import os, io, asyncio, threading, json, datetime as dt
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

import aiosqlite
import aiohttp

# --------- ENV ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_KEY     = os.getenv("OPENAI_API_KEY")
PAYPAL_CLIENT  = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET  = os.getenv("PAYPAL_SECRET", "")
PAYPAL_MODE    = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox|live
PRICE_PACK5    = float(os.getenv("PRICE_PACK5_USD", "3"))
PRICE_UNL      = float(os.getenv("PRICE_UNL_USD", "27"))
PORT           = int(os.getenv("PORT", "8000"))

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN is required")

# --------- OpenAI client ----------
client = None
if OPENAI_KEY:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_KEY)

SYSTEM_PROMPT = (
    "You are a helpful multilingual assistant for users in Israel. "
    "Answer in the user's language (RU/HE/EN) briefly and clearly."
)

# --------- DB ----------
DB_PATH = "bot.db"

async def db_init():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS meter(
            user_id INTEGER PRIMARY KEY,
            free_used INTEGER DEFAULT 0,
            pack_remaining INTEGER DEFAULT 0,
            unlimited_until TEXT  -- ISO date
        );
        CREATE TABLE IF NOT EXISTS payments(
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            plan TEXT,
            amount REAL,
            status TEXT,
            created_at TEXT
        );
        """)
        await db.commit()

async def get_meter(user_id:int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT free_used, pack_remaining, unlimited_until FROM meter WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row if row else (0, 0, None)

async def ensure_row(user_id:int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO meter(user_id) VALUES(?)", (user_id,))
        await db.commit()

async def add_use(user_id:int):
    await ensure_row(user_id)
    free_used, pack_rem, unlim = await get_meter(user_id)
    today = dt.date.today()
    unlim_ok = unlim and dt.date.fromisoformat(unlim) >= today
    async with aiosqlite.connect(DB_PATH) as db:
        if unlim_ok:
            # безлимит — счётчики не трогаем
            return
        elif pack_rem and pack_rem > 0:
            await db.execute("UPDATE meter SET pack_remaining=pack_remaining-1 WHERE user_id=?", (user_id,))
        else:
            await db.execute("UPDATE meter SET free_used=free_used+1 WHERE user_id=?", (user_id,))
        await db.commit()

async def check_access(user_id:int):
    """Возвращает ('ok', None) или ('pay', reason, kb_markup)"""
    await ensure_row(user_id)
    free_used, pack_rem, unlim = await get_meter(user_id)
    today = dt.date.today()
    if unlim and dt.date.fromisoformat(unlim) >= today:
        return ("ok", None, None)
    if free_used < 5:
        return ("ok", None, None)
    if pack_rem > 0:
        return ("ok", None, None)
    # Нет доступа — предложим оплату
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("Получить ещё 5 за $3", url=f"/pay?plan=pack5&u={user_id}")],
        [InlineKeyboardButton("Безлимит 30 дней — $27", url=f"/pay?plan=unl&u={user_id}")]
    ])
    return ("pay", "Доступ к ответам закончился. Выберите тариф:", kb)

async def grant_pack5(user_id:int, count:int=5):
    await ensure_row(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE meter SET pack_remaining=COALESCE(pack_remaining,0)+? WHERE user_id=?", (count, user_id))
        await db.commit()

async def grant_unlimited(user_id:int, days:int=30):
    await ensure_row(user_id)
    until = (dt.date.today() + dt.timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE meter SET unlimited_until=? WHERE user_id=?", (until, user_id))
        await db.commit()

# --------- PayPal helpers ----------
PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE=="sandbox" else "https://api-m.paypal.com"

async def paypal_token() -> str:
    if not PAYPAL_CLIENT or not PAYPAL_SECRET:
        raise RuntimeError("PAYPAL keys not set")
    auth = aiohttp.BasicAuth(PAYPAL_CLIENT, PAYPAL_SECRET)
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{PAYPAL_API_BASE}/v1/oauth2/token", data={"grant_type":"client_credentials"}, auth=auth) as r:
            data = await r.json()
            return data["access_token"]

async def paypal_create_order(plan:str, user_id:int) -> str:
    amount = PRICE_PACK5 if plan=="pack5" else PRICE_UNL
    token = await paypal_token()
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "custom_id": f"{plan}:{user_id}",
            "amount": {"currency_code":"USD", "value": f"{amount:.2f}"}
        }],
        "application_context": {
            "brand_name": "UniversalBot",
            "return_url": f"/pay/success?plan={plan}&u={user_id}",
            "cancel_url": f"/pay/cancel?plan={plan}&u={user_id}"
        }
    }
    async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"}) as s:
        async with s.post(f"{PAYPAL_API_BASE}/v2/checkout/orders", data=json.dumps(body)) as r:
            data = await r.json()
            if "id" not in data:
                raise RuntimeError(f"Create order failed: {data}")
            return data["id"]

async def paypal_capture_order(order_id:str) -> dict:
    token = await paypal_token()
    async with aiohttp.ClientSession(headers={"Authorization": f"Bearer {token}", "Content-Type":"application/json"}) as s:
        async with s.post(f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture") as r:
            return await r.json()

# --------- FastAPI (оплата) ----------
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

web = FastAPI()

@web.get("/", response_class=HTMLResponse)
async def root():
    return "<h3>Universal Bot API is running</h3>"

@web.get("/pay", response_class=HTMLResponse)
async def pay_page(plan: str, u: int):
    if plan not in ("pack5","unl"):
        return HTMLResponse("<h3>Unknown plan</h3>", status_code=400)
    price = PRICE_PACK5 if plan=="pack5" else PRICE_UNL
    cid = PAYPAL_CLIENT
    html = f"""
<!doctype html><html><head><meta charset="utf-8"><title>Оплата</title></head>
<body style="font-family:system-ui;max-width:560px;margin:40px auto;">
  <h2>Оплата плана: {"+5 вопросов" if plan=="pack5" else "Безлимит 30 дней"}</h2>
  <p>Сумма: <b>${price:.2f}</b></p>
  <div id="paypal-button"></div>
  <script src="https://www.paypal.com/sdk/js?client-id={cid}&currency=USD&intent=capture"></script>
  <script>
  paypal.Buttons({{
    createOrder: async function() {{
      const res = await fetch('/api/create-order', {{
        method: 'POST',
        headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{plan:'{plan}', user:{u}}})
      }});
      const data = await res.json();
      if(!data.orderID) throw new Error('order failed');
      return data.orderID;
    }},
    onApprove: async function(data) {{
      const res = await fetch('/api/capture-order', {{
        method: 'POST',
        headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{orderID: data.orderID}})
      }});
      const out = await res.json();
      if (out.status === 'COMPLETED') {{
        alert('Оплата прошла! Вернитесь в бота.');
        window.location.href = '/pay/success?plan={plan}&u={u}';
      }} else {{
        alert('Оплата не завершена');
      }}
    }}
  }}).render('#paypal-button');
  </script>
</body></html>
"""
    return HTMLResponse(html)

@web.post("/api/create-order")
async def api_create_order(req: Request):
    body = await req.json()
    plan = body.get("plan")
    user = int(body.get("user", 0))
    try:
        order_id = await paypal_create_order(plan, user)
        return JSONResponse({"orderID": order_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@web.post("/api/capture-order")
async def api_capture(req: Request):
    body = await req.json()
    order_id = body.get("orderID")
    data = await paypal_capture_order(order_id)
    # Простая валидация
    status = data.get("status")
    try:
        pu = data["purchase_units"][0]
        custom = pu.get("custom_id","")
        plan, user_str = custom.split(":")
        user_id = int(user_str)
    except:
        plan, user_id = "unknown", 0
    if status == "COMPLETED" and user_id:
        # записываем оплату и выдаём доступ
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR REPLACE INTO payments(id,user_id,plan,amount,status,created_at) VALUES(?,?,?,?,?,?)",
                             (order_id, user_id, plan, PRICE_PACK5 if plan=="pack5" else PRICE_UNL, status, dt.datetime.utcnow().isoformat()))
            await db.commit()
        if plan == "pack5":
            await grant_pack5(user_id, 5)
        else:
            await grant_unlimited(user_id, 30)
    return JSONResponse({"status": status, "plan": plan, "user": user_id})

@web.get("/pay/success")
async def pay_success(plan:str, u:int):
    return HTMLResponse(f"<h3>Оплата зафиксирована. Можно возвращаться в бота ✅</h3>")

@web.get("/pay/cancel")
async def pay_cancel(plan:str, u:int):
    return HTMLResponse(f"<h3>Оплата отменена.</h3>")

# --------- БОТ: меню/ИИ/медиа ----------
MENU = InlineKeyboardMarkup([
    [InlineKeyboardButton("🤖 ИИ‑чат", callback_data="ai")],
    [InlineKeyboardButton("💳 Оплата / тарифы", callback_data="pay")],
    [InlineKeyboardButton("💱 Курсы/обмен (скоро)", callback_data="fx")],
])

def chunk(s: str, n:int=4000):
    for i in range(0, len(s), n):
        yield s[i:i+n]

async def send_typing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)

def ai_sync(text:str)->str:
    if not client:
        return "ИИ временно недоступен. Админ подключит ключ."
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":text}],
        temperature=0.4, max_tokens=600
    )
    return r.choices[0].message.content.strip()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я универсальный бот. Пиши вопрос, отправляй фото/голос.", reply_markup=MENU)

async def menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "ai":
        await q.edit_message_text("Напиши вопрос — отвечу как ИИ. Лимиты: 5 бесплатно → +5 за $3 → безлимит $27.", reply_markup=MENU)
    elif q.data == "pay":
        u = q.from_user.id
        url1 = f"/pay?plan=pack5&u={u}"
        url2 = f"/pay?plan=unl&u={u}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Получить ещё 5 за $3", url=url1)],
            [InlineKeyboardButton("Безлимит 30 дней — $27", url=url2)],
        ])
        await q.edit_message_text("Тарифы и оплата PayPal:", reply_markup=kb)
    elif q.data == "fx":
        await q.edit_message_text("💱 Модуль обменников подключим следующим шагом.", reply_markup=MENU)

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state, reason, kb = await check_access(user_id)
    if state != "ok":
        await update.message.reply_text(reason, reply_markup=kb); return
    await send_typing(update, context)
    try:
        reply = await asyncio.to_thread(ai_sync, (update.message.text or ""))
    except Exception as e:
        reply = f"Ошибка ИИ: {e}"
    for part in chunk(reply):
        await update.message.reply_text(part)
    await add_use(user_id)

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state, reason, kb = await check_access(user_id)
    if state != "ok":
        await update.message.reply_text(reason, reply_markup=kb); return
    await send_typing(update, context)
    if not client:
        await update.message.reply_text("Получил фото ✅. Описание включим после подключения ИИ‑ключа."); return
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":"You are an image captioning assistant."},
                      {"role":"user","content":[{"type":"text","text":"Опиши изображение кратко."},
                                                {"type":"image_url","image_url":{"url":file_url}}]}],
            temperature=0.3, max_tokens=300
        )
        txt = r.choices[0].message.content.strip()
        await update.message.reply_text(txt or "Готово.")
    except Exception as e:
        await update.message.reply_text(f"Не удалось проанализировать фото: {e}")
    await add_use(user_id)

async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state, reason, kb = await check_access(user_id)
    if state != "ok":
        await update.message.reply_text(reason, reply_markup=kb); return
    await send_typing(update, context)
    if not client:
        await update.message.reply_text("Получил голосовое ✅. Расшифровку включим позже."); return
    voice = update.message.voice or update.message.audio
    tg_file = await context.bot.get_file(voice.file_id)
    buf = io.BytesIO(); await tg_file.download_to_memory(out=buf); buf.seek(0)
    try:
        tr = client.audio.transcriptions.create(model="whisper-1", file=("audio.ogg", buf, "audio/ogg"))
        text = tr.text.strip()
        reply = await asyncio.to_thread(ai_sync, text or "Пусто")
        for part in chunk(f"🗣 Распознал: {text}\n\n🤖 {reply}"):
            await update.message.reply_text(part)
    except Exception as e:
        await update.message.reply_text(f"Ошибка распознавания: {e}")
    await add_use(user_id)

async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Видео получил ✅. Расширенный анализ видео добавим позже.")

async def on_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Файл получил ✅. Скажи, что сделать (извлечь текст, переслать).")

def start_web():
    import uvicorn
    uvicorn.run(web, host="0.0.0.0", port=PORT, log_level="info")

def main():
    # web-сервер в отдельном потоке
    threading.Thread(target=start_web, daemon=True).start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CallbackQueryHandler(menu_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, on_voice))
    app.add_handler(MessageHandler(filters.VIDEO, on_video))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, on_doc))

    async def runner():
        await db_init()
        print("Universal bot is running with web server")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await app.updater.idle()

    asyncio.run(runner())

if __name__ == "__main__":
    main()
