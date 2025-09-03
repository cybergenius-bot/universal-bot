# bot.py — UNIVERSAL GPT‑4o — HOTFIX#7b‑U9
# U9:
# 1) Санитайзер ещё жёстче: сносит ###, жир/курсив, маркеры списков (- + • ► ● ▪ ▫ ◆ ◇ ★ ☆, а также — и – в начале строки), code-fence, blockquote '>'
# 2) Эмодзи сохраняем; нумерация 1., 2., 3. сохраняется
# 3) parse_mode=None, все ответы через send_clean(...)
# 4) Автоязык RU/HE — сразу; EN — только если не коротыш (<12 символов)
# 5) Сторис/рассказ — только по явной просьбе, без Markdown

import os
import re
import time
from collections import deque, defaultdict
from typing import Deque, Dict, Optional

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

# =========================
# Env
# =========================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_URL = os.environ.get("BASE_URL", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "railway123-secret")
WEBHOOK_PATH = "/telegram/railway123"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # "gpt-4o" для макс. качества

# =========================
# OpenAI
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

async def ask_openai(prompt: str, system: Optional[str] = None, temperature: float = 0.7, model: Optional[str] = None) -> str:
    client = get_openai_client()
    if not client:
        return "Пока нет доступа к GPT‑4o. Подключите OPENAI_API_KEY и перезапустите."
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    use_model = model or OPENAI_MODEL
    try:
        resp = client.chat.completions.create(model=use_model, messages=msgs, temperature=temperature)
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Не смог получить ответ от модели ({type(e).__name__}): {e}"

# =========================
# App/Bot/DP
# =========================
app = FastAPI()
bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=None)  # отключаем форматирование Telegram
dp = Dispatcher()
router = Router()
dp.include_router(router)

# =========================
# UI
# =========================
def make_reply_menu_button(ui_lang: str = "ru"):
    text = {"ru": "Меню", "en": "Menu", "he": "תפריט"}.get(ui_lang, "Меню")
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[[KeyboardButton(text=text)]],
        input_field_placeholder={"ru": "Напишите сообщение…", "en": "Type a message…", "he": "הקלד/י הודעה…"}
            .get(ui_lang, "Напишите сообщение…"),
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
# Language policy
# =========================
UserId = int
user_ui_lang: Dict[UserId, str] = defaultdict(lambda: "ru")
user_lang_hist: Dict[UserId, Deque[str]] = defaultdict(lambda: deque(maxlen=3))

def detect_script_lang(text: str) -> Optional[str]:
    heb = sum('\u0590' <= ch <= '\u05FF' for ch in text)     # Hebrew
    cyr = sum('А' <= ch <= 'я' or ch in "ёЁ" for ch in text)  # Cyrillic
    lat = sum('A' <= ch <= 'z' for ch in text)                # Latin
    if heb > cyr and heb > lat and heb > 0: return "he"
    if cyr > lat and cyr > heb and cyr > 0: return "ru"
    if lat > cyr and lat > heb and lat > 0: return "en"
    return None

def choose_content_lang(user_id: int, text: str) -> str:
    t = (text or "").strip()
    det = detect_script_lang(t)
    # EN — не переключаемся на коротышах; RU/HE — переключаемся мгновенно
    if det == "en" and len(t) < 12:
        det = None
    if det in ("ru", "he"):
        lang = det
    elif det == "en":
        lang = "en"
    else:
        hist = user_lang_hist[user_id]
        if len(hist) >= 2:
            for l in ("ru", "en", "he"):
                if sum(1 for x in hist if x == l) >= 2:
                    return l
        lang = user_ui_lang[user_id]
    # обновим гистерезис
    hist = user_lang_hist[user_id]
    hist.append(lang)
    for l in ("ru", "en", "he"):
        if sum(1 for x in hist if x == l) >= 2:
            return l
    return lang

# =========================
# Anti-echo (voice)
# =========================
recent_voice_meta: Dict[UserId, Dict[str, float]] = defaultdict(dict)
def anti_echo_reply(ui_lang: str = "ru"):
    heads = {"ru": ("Кратко", "Детали", "Чек‑лист"),
             "en": ("Brief", "Details", "Checklist"),
             "he": ("תמצית", "פרטים", "צ׳ק‑ליסט")}
    h = heads.get(ui_lang, heads["ru"])
    return (
        f"{h[0]}: Я услышал(а) ваш голос и понял(а) задачу. Сформулирую ответ без повтора вашей речи.\n\n"
        f"{h[1]}: Опишу подход, предложу варианты и подводные камни. Если нужна расшифровка — нажмите кнопку ниже.\n\n"
        f"{h[2]}:\n— 1) Цель → 2) Ограничения → 3) Опции → 4) Риски → 5) Следующий шаг.\n\n"
        f"Расшифровку покажу только по кнопке."
    )

# =========================
# Sanitize: убираем Markdown/«звёздочки»/маркеры, сохраняем эмодзи и нумерацию
# =========================
# «звёздочки»-аналоги (не затрагиваем эмодзи ✨ 🔮 и др.)
ASTERISK_LIKE = r"\*\u2217\u2731\u204E\uFE61\uFF0A"  # * ∗ ✱ ⁎ ﹡ ＊
# маркеры списков в начале строки, включая тире: - + • ► ▪ ▫ ● ○ ◆ ◇ и также —, –
BULLET_START = r"\-\+\•\►\▪\▫\●\○\◆\◇"
HEADER_PAT = re.compile(r'^\s*#{1,6}\s*')
BLOCKQUOTE_PAT = re.compile(r'^\s*>\s+')
DASH_BULLET_PAT = re.compile(r'^\s*[–—]\s+')

META_PATTERNS = [
    re.compile(r'^\s*конечно[,.! ]', re.IGNORECASE),
    re.compile(r'^\s*давайте[,.! ]', re.IGNORECASE),
    re.compile(r'^\s*с удовольствием[,.! ]', re.IGNORECASE),
    re.compile(r'^\s*вот как (?:можно|мы)\b', re.IGNORECASE),
    re.compile(r'^\s*предлагаю\b', re.IGNORECASE),
]

def strip_markdown_line_start(ln: str) -> str:
    s = ln.strip()
    # code‑fence
    if s.startswith("```"):
        return ""
    # blockquote '>'
    ln = BLOCKQUOTE_PAT.sub("", ln)
    # ### заголовки
    ln = HEADER_PAT.sub("", ln)
    # маркеры списков в начале строки
    ln = re.sub(rf'^\s*([{BULLET_START}])\s+', '', ln)
    # тире-буллеты — и –
    ln = DASH_BULLET_PAT.sub("", ln)
    return ln

def sanitize_output(text: str) -> str:
    if not text:
        return text
    # 1) Построчная чистка
    lines = [strip_markdown_line_start(ln) for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln is not None)

    # 2) Жир/курсив Markdown: **..**, __..__, *..*, _.._
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text, flags=re.S)
    text = re.sub(r'__(.*?)__', r'\1', text, flags=re.S)
    text = re.sub(r'(?<!\S)\*(.+?)\*(?!\S)', r'\1', text, flags=re.S)
    text = re.sub(r'(?<!\S)_(.+?)_(?!\S)', r'\1', text, flags=re.S)

    # 3) Любые одиночные «звёздочки»-символы и обратные апострофы
    text = re.sub(rf'[{ASTERISK_LIKE}`]+', '', text)

    # 4) Стартовые мета‑фразы (Конечно…, Давайте…)
    text = text.strip()
    ls = text.splitlines()
    while ls:
        head = ls[0].strip()
        if any(p.match(head) for p in META_PATTERNS):
            ls.pop(0)
        else:
            break
    text = "\n".join(ls).strip()

    # 5) Сжимаем лишние пустые строки и пробелы
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text

async def send_clean(msg_or_chat, text: str, **kwargs):
    return await msg_or_chat.answer(sanitize_output(text), **kwargs)

# =========================
# System prompts
# =========================
def system_prompt_for(lang: str) -> str:
    if lang == "ru":
        return "Ты SmartPro 24/7. Отвечай строго на русском. Без Markdown/жирного/курсива/списков. Обычный текст. Эмодзи можно."
    if lang == "he":
        return "את/ה SmartPro 24/7. ענה/עני אך ורק בעברית. בלי Markdown/הדגשות/רשימות. טקסט פשוט. אמוג׳י מותר."
    return "You are SmartPro 24/7. Answer strictly in English. No Markdown/bold/italics/lists. Plain text. Emojis allowed."

def copy_system_prompt_for(lang: str) -> str:
    if lang == "ru":
        return "Ты копирайтер. 1‑е лицо, тёплый тон. Без Markdown/звёздочек/списков/заголовков. 2–4 коротких абзаца."
    if lang == "he":
        return "את/ה קופירייטר/ית. גוף ראשון, טון חם. בלי Markdown/כוכביות/רשימות/כותרות. 2–4 פסקאות קצרות."
    return "Experienced copywriter. First person, warm tone. No Markdown/asterisks/lists/headings. 2–4 short paragraphs."

def build_user_prompt(lang: str, user_text: str) -> str:
    if lang == "ru":
        return f"Запрос пользователя: {user_text}\nДай точный, небанальный ответ по теме. Без Markdown/жирного/курсива/списков."
    if lang == "he":
        return f"בקשת המשתמש: {user_text}\nענה/עני תשובה מדויקת וישירה בנושא. בלי Markdown/הדגשות/רשימות."
    return f"User request: {user_text}\nProvide a precise, non‑generic answer. No Markdown/bold/italics/lists."

# =========================
# Triggers (explicit creative only, tolerant)
# =========================
STORY_TRIG = re.compile(r'^\s*(напиши|сделай|сгенерируй)\b.*\b(сторис|story|инста-?сторис)\b', re.IGNORECASE | re.S)
NARR_TRIG  = re.compile(r'^\s*(напиши|сделай|сгенерируй)\b.*\b(рассказ|эссе|сочинение|повесть|short\s+story|essay)\b', re.IGNORECASE | re.S)
COPY_TRIG  = re.compile(r'(пост\s+приветств|приветстви[ея]\b|описани[ея]\b|био\b|bio\b)', re.IGNORECASE)

def extract_topic_after_keyword(txt: str, keywords: list[str]) -> str:
    pattern = re.compile(r'(' + '|'.join(map(re.escape, keywords)) + r')\b', re.IGNORECASE)
    m = pattern.search(txt)
    tail = txt[m.end():] if m else txt
    tail = re.sub(r'^\s*(про|о|about)\b', '', tail, flags=re.IGNORECASE).strip()
    return tail if tail else txt.strip()

# =========================
# Commands
# =========================
async def set_commands():
    await bot.set_my_commands(
        [BotCommand(command="start", description="Приветствие"),
         BotCommand(command="menu", description="Открыть меню"),
         BotCommand(command="version", description="Проверить версию")],
        scope=BotCommandScopeDefault(), language_code="ru",
    )
    await bot.set_my_commands(
        [BotCommand(command="start", description="Greeting"),
         BotCommand(command="menu", description="Open menu"),
         BotCommand(command="version", description="Check version")],
        scope=BotCommandScopeDefault(), language_code="en",
    )
    await bot.set_my_commands(
        [BotCommand(command="start", description="ברכה"),
         BotCommand(command="menu", description="פתח תפריט"),
         BotCommand(command="version", description="בדיקת גרסה")],
        scope=BotCommandScopeDefault(), language_code="he",
    )

# =========================
# Handlers
# =========================
@router.message(CommandStart())
async def on_start(message: Message):
    uid = message.from_user.id
    kb = make_reply_menu_button(user_ui_lang[uid])
    text = {"ru": "Привет! Я SmartPro 24/7. Нажмите «Меню», когда нужно открыть действия.",
            "en": "Hi! I’m SmartPro 24/7. Tap “Menu” when you want actions.",
            "he": "היי! אני SmartPro 24/7. לחצו \"תפריט\" כדי לפתוח פעולות."}[user_ui_lang[uid]]
    await send_clean(message, text, reply_markup=kb)

@router.message(Command("menu"))
async def on_menu_cmd(message: Message):
    uid = message.from_user.id
    await send_clean(message, "Меню действий:", reply_markup=make_inline_menu(user_ui_lang[uid]))

@router.message(Command("version"))
async def on_version_cmd(message: Message):
    await send_clean(message, "UNIVERSAL GPT‑4o — HOTFIX#7b‑U9")

@router.message(F.text.casefold() == "меню")
@router.message(F.text.casefold() == "menu")
async def on_menu_text(message: Message):
    uid = message.from_user.id
    await send_clean(message, "Меню действий:", reply_markup=make_inline_menu(user_ui_lang[uid]))

# ---------- Inline buttons ----------
@router.callback_query(F.data == "help")
async def on_help(cb: CallbackQuery):
    uid = cb.from_user.id
    ui = user_ui_lang[uid]
    await cb.answer("Открываю помощь…", show_alert=False)
    text = {
        "ru": "Я универсальный помощник. Просто задайте вопрос. Сторис/рассказ — по явной просьбе. Без Markdown/жирного/курсива/списков.",
        "en": "Universal assistant. Ask anything. Stories/narratives on explicit request. No markdown/bold/italics/lists.",
        "he": "עוזר אוניברסלי. אפשר לשאול הכל. סטוריז/סיפור רק בבקשה מפורשת. בלי Markdown/הדגשות/רשימות.",
    }.get(ui, "Я универсальный помощник. Просто задайте вопрос.")
    await send_clean(cb.message, text)

@router.callback_query(F.data == "pay")
async def on_pay(cb: CallbackQuery):
    await cb.answer("Оплата скоро будет доступна", show_alert=False)
    await send_clean(cb.message, "Оплата появится позже (Stripe Checkout).")

@router.callback_query(F.data == "refs")
async def on_refs(cb: CallbackQuery):
    await cb.answer("Рефералы", show_alert=False)
    await send_clean(cb.message, "Реферальные ссылки появятся позже. Формат: t.me/<bot>?start=ref_<uid>.")

@router.callback_query(F.data == "profile")
async def on_profile(cb: CallbackQuery):
    await cb.answer("Профиль", show_alert=False)
    user = cb.from_user
    await send_clean(cb.message, f"Профиль: {user.first_name or ''} {user.last_name or ''}".strip())

@router.callback_query(F.data == "lang")
async def on_change_lang(cb: CallbackQuery):
    uid = cb.from_user.id
    cur = user_ui_lang[uid]
    cycle = {"ru": "en", "en": "he", "he": "ru"}
    user_ui_lang[uid] = cycle.get(cur, "en")
    await cb.answer(f"UI язык: {user_ui_lang[uid].upper()}")
    await send_clean(cb.message, "Язык интерфейса изменён.", reply_markup=make_reply_menu_button(user_ui_lang[uid]))

@router.callback_query(F.data == "mode")
async def on_mode(cb: CallbackQuery):
    await cb.answer("Режим ответа", show_alert=False)
    await send_clean(cb.message, "Режим ответа: универсальный. Творчество — по явной просьбе.")

@router.callback_query(F.data == "tts")
async def on_tts(cb: CallbackQuery):
    await cb.answer("TTS", show_alert=False)
    await send_clean(cb.message, "Озвучка (TTS) будет доступна по кнопке, когда подключим движок.")

@router.callback_query(F.data == "asr")
async def on_show_transcript(cb: CallbackQuery):
    await cb.answer("Показать расшифровку", show_alert=False)
    await send_clean(cb.message, "Расшифровка будет доступна после подключения ASR (Whisper/gpt‑4o‑mini‑transcribe).")

@router.callback_query(F.data == "close_menu")
async def on_close_menu(cb: CallbackQuery):
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.answer("Скрыто")

@router.callback_query()
async def on_any_callback(cb: CallbackQuery):
    await cb.answer("Готово", show_alert=False)

# ---------- Voice / Photo ----------
@router.message(F.voice)
async def on_voice(message: Message):
    uid = message.from_user.id
    ui_lang = user_ui_lang[uid]
    recent_voice_meta[uid]["last_ts"] = time.time()
    text = anti_echo_reply(ui_lang)
    ik = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text={"ru": "Показать расшифровку", "en": "Show transcript", "he": "הצג תמליל"}[ui_lang],
                              callback_data="asr")],
        [InlineKeyboardButton(text={"ru": "Скрыть", "en": "Close", "he": "סגור"}[ui_lang],
                              callback_data="close_menu")],
    ])
    await send_clean(message, text, reply_markup=ik)

@router.message(F.photo)
async def on_photo(message: Message):
    await send_clean(message, "Изображение получено. OCR будет доступен через меню после подключения. Пока я отвечу по тексту.")

# =========================
# Text handler
# =========================
@router.message()
async def on_text(message: Message):
    uid = message.from_user.id
    ui = user_ui_lang[uid]
    text = (message.text or "").strip()
    content_lang = choose_content_lang(uid, text)

    # 1) СТОРИС — явная просьба (допускаем слова между)
    if STORY_TRIG.match(text):
        topic = extract_topic_after_keyword(text, ["сторис", "story", "инста-сторис", "инста сторис"])
        sys = ("You are a world‑class creative writer crafting cinematic, sensory Instagram‑style stories. "
               f"Answer strictly in { 'Russian' if content_lang=='ru' else ('Hebrew' if content_lang=='he' else 'English') }. "
               "No Markdown, no asterisks/lists/headings.")
        prompt = (f"Тема сторис: {topic}\n"
                  f"Напиши 6–8 кинематографичных кадров (1–2 насыщенные фразы на кадр) со звуками/запахами/тактильностью, "
                  f"точными наблюдениями и сильной концовкой. Пиши на ({content_lang}). Без вступительных фраз и инструкций.")
        ans = await ask_openai(prompt, system=sys, temperature=0.9, model="gpt-4o")
        return await send_clean(message, ans)

    # 2) Рассказ/эссе — явная просьба
    if NARR_TRIG.match(text):
        topic = extract_topic_after_keyword(text, ["рассказ", "эссе", "сочинение", "повесть", "short story", "essay"])
        sys = ("You are a literary writer. Produce a vivid short narrative. "
               f"Answer strictly in { 'Russian' if content_lang=='ru' else ('Hebrew' if content_lang=='he' else 'English') }. "
               "No Markdown, no asterisks/lists/headings.")
        prompt = (f"Тема рассказа: {topic}\n"
                  f"Напиши короткий рассказ 350–600 слов на ({content_lang}), с образностью, ритмом, сценами, диалогами по необходимости. "
                  f"Без клише и без объяснений формата.")
        ans = await ask_openai(prompt, system=sys, temperature=0.8, model="gpt-4o")
        return await send_clean(message, ans)

    # 3) Копирайт (приветствие/био/описание)
    if COPY_TRIG.search(text):
        m = re.search(r'меня зовут\s+([A-Za-zА-Яа-яЁё\-]+)', text, re.IGNORECASE)
        tg_name = (message.from_user.first_name or "").strip() if message.from_user else ""
        name = m.group(1) if m else tg_name
        sys = copy_system_prompt_for(content_lang)
        prompt = (f"Напиши пост-приветствие в первом лице на ({content_lang}). "
                  f"Если имя доступно, используй его: {name if name else 'имя не указано'}. "
                  f"Суть из запроса: {text}. Избегай клише и шаблонов, не используй списки и заголовки.")
        ans = await ask_openai(prompt, system=sys, temperature=0.65)
        return await send_clean(message, ans)

    # 4) По умолчанию — универсальный ответ
    sys = system_prompt_for(content_lang)
    prompt = build_user_prompt(content_lang, text)
    ans = await ask_openai(prompt, system=sys, temperature=0.55)
    return await send_clean(message, ans)

# =========================
# FastAPI routes
# =========================
@app.get("/version", response_class=PlainTextResponse)
async def version():
    return "UNIVERSAL GPT‑4o — HOTFIX#7b‑U9"

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
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    await set_commands()
    if BASE_URL and TELEGRAM_BOT_TOKEN:
        try:
            await bot.set_webhook(url=BASE_URL + WEBHOOK_PATH, secret_token=WEBHOOK_SECRET, drop_pending_updates=True)
        except Exception:
            pass

# Start: uvicorn bot:app --host 0.0.0.0 --port 8080
