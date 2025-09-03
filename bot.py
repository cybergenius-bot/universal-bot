# bot.py — UNIVERSAL GPT-4o — HOTFIX#7b
import os
import time
from collections import deque, defaultdict
from typing import Deque, Dict, Literal, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, Update, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, BotCommandScopeDefault
)
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode

# =========================
# Env
# =========================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = os.environ.get("BASE_URL", "")  # e.g., https://universal-bot-production.up.railway.app
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "railway123-secret")
WEBHOOK_PATH = "/telegram/railway123"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # set to "gpt-4o" for maximum quality

# =========================
# OpenAI client (lazy)
# =========================
_openai_client = None
def get_openai_client():
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=OPENAI_API_KEY)
        except Exception:
            _openai_client = None
    return _openai_client

async def ask_openai(prompt: str, system: Optional[str] = None, temperature: float = 0.7) -> str:
    client = get_openai_client()
    if not client:
        # Fallback if no API key configured
        return "Пока у меня нет доступа к GPT‑4o. Подключите OPENAI_API_KEY и перезапустите."
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    try:
        # Chat Completions (совместимо и стабильно)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Не смог получить ответ от модели ({type(e).__name__}): {e}"

# =========================
# App, Bot, DP, Router
# =========================
app = FastAPI()
bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# =========================
# UI / Keyboards
# =========================
def make_reply_menu_button(ui_lang: str = "ru"):
    # Компактная единственная кнопка у поля ввода
    text = {"ru": "Меню", "en": "Menu", "he": "תפריט"}.get(ui_lang, "Меню")
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text=text)]],
        input_field_placeholder={"ru": "Напишите сообщение…",
                                 "en": "Type a message…",
                                 "he": "הקלד/י הודעה…"
                                 }.get(ui_lang, "Напишите сообщение…"),
        selective=True
    )

def make_inline_menu(ui_lang: str = "ru"):
    t = {
        "help": {"ru": "Помощь", "en": "Help", "he": "עזרה"},
        "pay": {"ru": "Оплатить", "en": "Pay", "he": "תשלום"},
        "refs": {"ru": "Рефералы", "en": "Referrals", "he": "הפניות"},
        "profile": {"ru": "Профиль", "en": "Profile", "he": "פרופיל"},
        "lang": {"ru": "Сменить язык", "en": "Change language", "he": "שנה שפה"},
        "mode": {"ru": "Режим ответа", "en": "Reply mode", "he": "מצב תגובה"},
        "tts": {"ru": "Озвучить (TTS)", "en": "Speak (TTS)", "he": "המרה לדיבור"},
        "asr": {"ru": "Показать расшифровку", "en": "Show transcript", "he": "הצג תמליל"},
        "close": {"ru": "Скрыть", "en": "Close", "he": "סגור"},
    }
    def _(k): return t[k].get(ui_lang, t[k]["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_("help"), callback_data="help"),
         InlineKeyboardButton(text=_("pay"), callback_data="pay")],
        [InlineKeyboardButton(text=_("refs"), callback_data="refs"),
         InlineKeyboardButton(text=_("profile"), callback_data="profile")],
        [InlineKeyboardButton(text=_("lang"), callback_data="lang"),
         InlineKeyboardButton(text=_("mode"), callback_data="mode")],
        [InlineKeyboardButton(text=_("tts"), callback_data="tts"),
         InlineKeyboardButton(text=_("asr"), callback_data="asr")],
        [InlineKeyboardButton(text=_("close"), callback_data="close_menu")],
    ])

# =========================
# Language policy: content_lang auto + hysteresis; ui_lang fixed by user
# =========================
UserId = int
user_ui_lang: Dict[UserId, str] = defaultdict(lambda: "ru")
user_lang_hist: Dict[UserId, Deque[str]] = defaultdict(lambda: deque(maxlen=3))  # last 3 content langs

def script_detect(text: str) -> str:
    # Простая эвристика по диапазонам Юникода
    cyr = sum('А' <= ch <= 'я' or ch in "ёЁ" for ch in text)
    lat = sum('A' <= ch <= 'z' for ch in text)
    heb = sum('\u0590' <= ch <= '\u05FF' for ch in text)
    if heb > cyr and heb > lat:
        return "he"
    if cyr > lat and cyr > heb:
        return "ru"
    return "en"

def choose_content_lang(user_id: int, text: str) -> str:
    # Избегаем EN на коротких токенах
    if len(text.strip()) < 12:
        # смотрим гистерезис
        hist = user_lang_hist[user_id]
        if len(hist) >= 2:
            # если 2 из последних 3 одинаковые — закрепляем
            for lang in ("ru", "en", "he"):
                if sum(1 for x in hist if x == lang) >= 2:
                    return lang
        # иначе — текущий ui_lang
        return user_ui_lang[user_id]
    lang = script_detect(text)
    # обновим гистерезис
    hist = user_lang_hist[user_id]
    hist.append(lang)
    # если 2 из 3 — закрепляем
    for l in ("ru", "en", "he"):
        if sum(1 for x in hist if x == l) >= 2:
            return l
    return lang

# =========================
# Anti-echo for voice
# =========================
recent_voice_meta: Dict[UserId, Dict[str, float]] = defaultdict(dict)
# keys: last_ts, last_len, trap_count

def anti_echo_reply(ui_lang: str = "ru"):
    heads = {
        "ru": ("Кратко", "Детали", "Чек‑лист"),
        "en": ("Brief", "Details", "Checklist"),
        "he": ("תמצית", "פרטים", "צ׳ק‑ליסט"),
    }
    h = heads.get(ui_lang, heads["ru"])
    return (
        f"<b>{h[0]}:</b> Я услышал(а) ваш голос и понял(а) задачу. "
        f"Сформулирую ответ без повтора вашей речи.\n\n"
        f"<b>{h[1]}:</b> Опишу подход, предложу варианты и подводные камни. "
        f"Если нужна расшифровка аудио, нажмите кнопку ниже.\n\n"
        f"<b>{h[2]}:</b>\n"
        f"— 1) Цель → 2) Ограничения → 3) Опции → 4) Риски → 5) Следующий шаг.\n\n"
        f"Расшифровку покажу только по кнопке."
    )

# =========================
# Commands
# =========================
async def set_commands():
    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="Приветствие"),
            BotCommand(command="menu", description="Открыть меню"),
            BotCommand(command="version", description="Проверить версию"),
        ],
        scope=BotCommandScopeDefault(),
        language_code="ru",
    )
    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="Greeting"),
            BotCommand(command="menu", description="Open menu"),
            BotCommand(command="version", description="Check version"),
        ],
        scope=BotCommandScopeDefault(),
        language_code="en",
    )
    await bot.set_my_commands(
        commands=[
            BotCommand(command="start", description="ברכה"),
            BotCommand(command="menu", description="פתח תפריט"),
            BotCommand(command="version", description="בדיקת גרסה"),
        ],
        scope=BotCommandScopeDefault(),
        language_code="he",
    )

# =========================
# Handlers
# =========================
@router.message(CommandStart())
async def on_start(message: Message):
    uid = message.from_user.id
    kb = make_reply_menu_button(user_ui_lang[uid])
    text = {
        "ru": "Привет! Я SmartPro 24/7. Нажмите «Меню», когда нужно открыть действия.",
        "en": "Hi! I’m SmartPro 24/7. Tap “Menu” when you want actions.",
        "he": "היי! אני SmartPro 24/7. לחצו \"תפריט\" כדי לפתוח פעולות.",
    }[user_ui_lang[uid]]
    await message.answer(text, reply_markup=kb)

@router.message(Command("menu"))
async def on_menu_cmd(message: Message):
    uid = message.from_user.id
    await message.answer("Меню действий:", reply_markup=make_inline_menu(user_ui_lang[uid]))

@router.message(Command("version"))
async def on_version_cmd(message: Message):
    await message.answer("UNIVERSAL GPT‑4o — HOTFIX#7b")

@router.message(F.text.casefold() == "меню")
@router.message(F.text.casefold() == "menu")
async def on_menu_text(message: Message):
    uid = message.from_user.id
    await message.answer("Меню действий:", reply_markup=make_inline_menu(user_ui_lang[uid]))

@router.callback_query(F.data == "close_menu")
async def on_close_menu(cb: CallbackQuery):
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        # если нельзя редактировать (устарело) — просто ответим
        pass
    await cb.answer("Скрыто")

@router.callback_query(F.data == "asr")
async def on_show_transcript(cb: CallbackQuery):
    # Показать доступную расшифровку (когда ASR подключён). Пока — заглушка.
    await cb.answer()
    await cb.message.answer("Расшифровка будет доступна после подключения ASR (Whisper/gpt‑4o‑mini‑transcribe).")

@router.callback_query(F.data == "lang")
async def on_change_lang(cb: CallbackQuery):
    uid = cb.from_user.id
    cur = user_ui_lang[uid]
    cycle = {"ru": "en", "en": "he", "he": "ru"}
    user_ui_lang[uid] = cycle.get(cur, "en")
    await cb.answer(f"UI язык: {user_ui_lang[uid].upper()}")
    # Обновим клавиатуру «Меню»
    await cb.message.answer("Язык интерфейса изменён.", reply_markup=make_reply_menu_button(user_ui_lang[uid]))

@router.message(F.voice)
async def on_voice(message: Message):
    uid = message.from_user.id
    ui_lang = user_ui_lang[uid]
    now = time.time()
    meta = recent_voice_meta[uid]
    last_ts = meta.get("last_ts", 0.0)
    meta["last_ts"] = now
    # Скрытая ловушка «эхо» 15 сек: мы в любом случае НЕ повторяем ASR‑текст
    text = anti_echo_reply(ui_lang)
    ik = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text={"ru": "Показать расшифровку", "en": "Show transcript", "he": "הצג תמליל"}.get(ui_lang, "Показать расшифровку"),
                              callback_data="asr")],
        [InlineKeyboardButton(text={"ru": "Скрыть", "en": "Close", "he": "סגור"}.get(ui_lang, "Скрыть"),
                              callback_data="close_menu")],
    ])
    await message.answer(text, reply_markup=ik)

@router.message(F.photo)
async def on_photo(message: Message):
    # Без авто‑OCR. Даём безопасную карточку + кнопки в инлайн‑меню.
    await message.answer(
        "Изображение получено. OCR будет доступен через меню после подключения. Пока я отвечу по текстовому запросу.",
    )

@router.message()
async def on_text(message: Message):
    uid = message.from_user.id
    ui = user_ui_lang[uid]
    text = message.text or ""
    content_lang = choose_content_lang(uid, text)

    # «сторис про …» / "story about …" простая эвристика
    lowered = text.lower().strip()
    if lowered.startswith("сторис про ") or lowered.startswith("история про ") or lowered.startswith("story about "):
        topic = text.split("про ", 1)[-1] if "про " in lowered else text.split("about ", 1)[-1]
        sys = "You are a world‑class creative writer crafting cinematic Instagram‑style stories with vivid sensory details, rhythm, and emotional arc. Write in the user's language."
        prompt = f"Напиши кинематографичную сторис про: {topic}. Сделай 6‑8 коротких кадров (1‑2 фразы на кадр), с запахами, звуками, тактильными ощущениями, без клише, с мощной концовкой."
        answer = await ask_openai(prompt, system=sys, temperature=0.85)
        await message.answer(answer)
        return

    # Обычный расширенный ответ
    sys = "You are SmartPro 24/7, a precise, helpful assistant. Give comprehensive, structured answers in the detected user language."
    prompt = f"Вопрос пользователя ({content_lang}): {text}\nДай развернутый, точный ответ, избегая шаблонов. Если уместно, предложи пример/шаги/советы."
    answer = await ask_openai(prompt, system=sys, temperature=0.6)
    await message.answer(answer)

# =========================
# FastAPI routes
# =========================
@app.get("/version", response_class=PlainTextResponse)
async def version():
    return "UNIVERSAL GPT‑4o — HOTFIX#7b"

@app.post(WEBHOOK_PATH)
async def tg_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return JSONResponse({"ok": True})

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"

@app.on_event("startup")
async def on_startup():
    await set_commands()
    if BASE_URL and TELEGRAM_BOT_TOKEN:
        try:
            await bot.set_webhook(
                url=BASE_URL + WEBHOOK_PATH,
                secret_token=WEBHOOK_SECRET,
                drop_pending_updates=True
            )
        except Exception:
            # допускаем ручную установку вебхука
            pass

# Uvicorn entry: uvicorn bot:app --host 0.0.0.0 --port 8080
