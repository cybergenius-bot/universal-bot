# SmartPro 24/7 — UNIVERSAL GPT‑4o, HOTFIX#7 (Greeting + Full /menu + Stories + Anti‑Echo)
# — Приветствие на /start (ничего не «выпрыгивает» само)
# — /menu: полное inline‑меню (Help, Pay, Referrals, Profile, Change language, Reply mode, TTS, Show transcript, Close)
# — Текстовые ответы: GPT‑4o/4o‑mini, без эха, структурно и обширно (режимы: Кратко/Развёрнуто/Глубоко)
# — Stories: “сторис про …” генерирует богатые кадры через GPT
# — Голос: анти‑эхо (без повтора речи), ASR пока отключён
# — /version и HTTP GET /version показывают текущую версию

import os, re, time, asyncio, tempfile, subprocess
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, Update, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile,
)
from gtts import gTTS
import imageio_ffmpeg

# -------- OpenAI (GPT‑4o) --------
from openai import OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # можно gpt-4o для лучшего качества
oai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# -------- Telegram / FastAPI конфиг --------
TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
SECRET = os.getenv("WEBHOOK_SECRET") or os.getenv("TELEGRAM_WEBHOOK_SECRET", "railway123")
BASE   = os.getenv("BASE_URL") or os.getenv("PUBLIC_BASE_URL", "")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

bot = Bot(TOKEN)
dp  = Dispatcher()
app = FastAPI()

VERSION = "UNIVERSAL GPT‑4o — HOTFIX#7"
BOT_USERNAME = ""

# -------- In‑memory состояние --------
ui_lang: dict[int, str] = {}                 # RU/EN/HE
reply_mode: dict[int, str] = {}              # short/expanded/deep
last_content_langs: dict[int, list[str]] = {}
content_lang: dict[int, str] = {}
_asr_store: dict[int, str] = {}
_last_voice_at: dict[int, float] = {}
_last_asr_text: dict[int, str] = {}

# -------- Локализация UI --------
def t_ui(lang: str = "ru"):
    data = {
        "ru": dict(
            hello=(
                "Привет! Я SmartPro 24/7 — универсальный помощник на GPT‑4o для текста, голоса и медиа.\n"
                "Что могу: Stories, идеи/названия, большие разборы, навигация по темам, карточки фото/видео (OCR позже).\n"
                "Откройте действия командой /menu. Пишите как удобно — отвечу на языке запроса."
            ),
            menu_title="Меню действий",
            help="Помощь",
            pay="Оплатить",
            refs="Рефералы",
            profile="Профиль",
            lang="Сменить язык",
            mode="Режим ответа",
            say="Дай голосом",
            show_tr="Показать расшифровку",
            close="Скрыть",
            mode_choose="Выберите стиль ответа:",
            mode_saved="Режим ответа сохранён.",
            mode_short="Кратко",
            mode_expanded="Развёрнуто",
            mode_deep="Глубоко",
            lang_choose="Выберите язык интерфейса:",
            lang_saved="Язык интерфейса сохранён.",
            tts_caption="Озвучено",
            pay_stub="Оплаты включим после UAT (Stripe USD $10/$20/$50).",
            refs_stub="Ваша реф‑ссылка:\n{link}\nБонус: +3 за каждого платящего друга.",
            profile_stub="Профиль:\n— UI язык: {ui}\n— Режим ответа: {mode}\n— Язык контента: {cl}\n— Версия: {ver}",
            no_transcript="Расшифровка пока недоступна (ASR отключён).",
            voice_hint="Голос получен. Распознавание временно отключено — отвечаю без повтора. Для действий откройте /menu.",
        ),
        "en": dict(
            hello="Hi! I’m SmartPro 24/7 — a GPT‑4o universal assistant for text, voice and media. Use /menu to open actions.",
            menu_title="Actions menu",
            help="Help", pay="Pay", refs="Referrals", profile="Profile",
            lang="Change language", mode="Reply mode",
            say="Speak it", show_tr="Show transcript", close="Hide",
            mode_choose="Choose reply style:", mode_saved="Reply mode saved.",
            mode_short="Short", mode_expanded="Expanded", mode_deep="In‑depth",
            lang_choose="Choose interface language:", lang_saved="Interface language saved.",
            tts_caption="Voiced",
            pay_stub="Payments after UAT (Stripe USD $10/$20/$50).",
            refs_stub="Your referral link:\n{link}\nBonus: +3 per paying friend.",
            profile_stub="Profile:\n— UI lang: {ui}\n— Reply mode: {mode}\n— Content lang: {cl}\n— Version: {ver}",
            no_transcript="Transcript not available yet (ASR disabled).",
            voice_hint="Voice received. ASR disabled for now — replying without echo. Use /menu for actions.",
        ),
        "he": dict(
            hello="שלום! אני SmartPro 24/7 עם GPT‑4o. פתחו /menu לפעולות.",
            menu_title="תפריט פעולות",
            help="עזרה", pay="לתשלום", refs="הפניות", profile="פרופיל",
            lang="החלפת שפה", mode="מצב תגובה",
            say="השמע בקול", show_tr="הצג תמלול", close="סגור",
            mode_choose="בחרו סגנון תשובה:", mode_saved="מצב התגובה נשמר.",
            mode_short="קצר", mode_expanded="מורחב", mode_deep="מעמיק",
            lang_choose="בחרו שפת ממשק:", lang_saved="שפת הממשק נשמרה.",
            tts_caption="הוקרא",
            pay_stub="תשלומים לאחר UAT (Stripe USD $10/$20/$50).",
            refs_stub="קישור ההפניה שלך:\n{link}\nבונוס: +3 על כל חבר משלם.",
            profile_stub="פרופיל:\n— שפת UI: {ui}\n— מצב תגובה: {mode}\n— שפת תוכן: {cl}\n— גרסה: {ver}",
            no_transcript="אין עדיין תמלול (ASR כבוי).",
            voice_hint="הודעה קולית התקבלה. ASR כבוי — עונה ללא הדהוד. /menu לפעולות.",
        ),
    }
    return data.get(lang, data["ru"])

def inline_main_menu(lang: str = "ru"):
    t = t_ui(lang)
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["help"],   callback_data="m_help"),
         InlineKeyboardButton(text=t["pay"],    callback_data="m_pay"),
         InlineKeyboardButton(text=t["refs"],   callback_data="m_refs")],
        [InlineKeyboardButton(text=t["profile"],callback_data="m_profile"),
         InlineKeyboardButton(text=t["lang"],   callback_data="m_lang"),
         InlineKeyboardButton(text=t["mode"],   callback_data="m_mode")],
        [InlineKeyboardButton(text=t["say"],    callback_data="m_say"),
         InlineKeyboardButton(text=t["show_tr"],callback_data="m_showtr")],
        [InlineKeyboardButton(text=t["close"],  callback_data="m_close")],
    ])

# -------- Автоязык контента + гистерезис --------
rx = {
    "ru": re.compile(r"[А-Яа-яЁё]"),
    "he": re.compile(r"[א-ת]"),
    "ar": re.compile(r"[\u0600-\u06FF]"),
    "ja": re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]"),
    "ko": re.compile(r"[\uAC00-\uD7AF]"),
    "zh": re.compile(r"[\u4E00-\u9FFF]"),
    "en": re.compile(r"[A-Za-z]"),
}
def detect_script_lang(text: str) -> str | None:
    for code, pat in rx.items():
        if pat.search(text or ""):
            return code
    return None

def update_content_lang(uid: int, candidate: str) -> str:
    arr = last_content_langs.get(uid, [])
    arr.append(candidate)
    if len(arr) > 3: arr.pop(0)
    last_content_langs[uid] = arr
    cnt = {}
    for c in arr: cnt[c] = cnt.get(c, 0) + 1
    best = max(cnt, key=cnt.get)
    if cnt[best] >= 2:
        content_lang[uid] = best
    return content_lang.get(uid, candidate)

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()

def ensure_profile(uid: int):
    if uid not in ui_lang:    ui_lang[uid] = "ru"
    if uid not in reply_mode: reply_mode[uid] = "expanded"

# -------- Анти‑эхо «рыба» для войса --------
async def _anti_echo_text(lang: str, mode: str) -> str:
    if mode not in ("short","expanded","deep"):
        mode = "expanded"
    if lang == "he":
        base = {"short":"תקציר: קיבלתי. בלי הדהוד.",
                "expanded":"תקציר: תשובה עניינית ללא הדהוד.",
                "deep":"מעמיק: הקשר ושלבים — ללא הדהוד."}
        return base[mode]
    if lang == "en":
        base = {"short":"Summary: received. No echo.",
                "expanded":"Summary: to the point, no echo.",
                "deep":"In‑depth: context and next steps — no echo."}
        return base[mode]
    base = {"short":"Кратко: запрос принят. Без повтора слов.",
            "expanded":"Развёрнуто: по сути, не повторяя ваш текст.",
            "deep":"Глубоко: контекст и шаги — без повтора речи."}
    return base[mode]

# -------- GPT‑4o генерация --------
SYSTEM_CORE_RU = (
    "Ты — SmartPro 24/7 на GPT‑4o. Правила:\n"
    "— Не повторяй дословно запрос пользователя (никакого эха).\n"
    "— Отвечай на языке запроса. Структура по режиму: "
    "Кратко (3–5 пунктов) / Развёрнуто (2–3 абзаца + список действий) / Глубоко (контекст, пошаговый план, риски).\n"
    "— Уместные примеры, конкретика, без воды. Для Stories — 4–7 кадров, живые детали, сцены, ритуалы, чек‑лист, CTA.\n"
    "— Никаких выдумок о фото/видео, если распознавание не подключено.\n"
)
SYSTEM_CORE_EN = (
    "You are SmartPro 24/7 powered by GPT‑4o. Rules:\n"
    "— Never echo the user’s text.\n"
    "— Answer in the user’s language. Styles: Short (3–5 bullets) / Expanded (2–3 paragraphs + actions) / In‑depth (context, step‑by‑step, risks).\n"
    "— Be concrete; add examples. For Stories: 4–7 frames, vivid details, scene, ritual, checklist, CTA.\n"
    "— Do not invent image/video content if recognition is disabled.\n"
)

def system_prompt_for_lang(lang: str) -> str:
    return SYSTEM_CORE_EN if lang == "en" else SYSTEM_CORE_RU

async def gpt_answer(user_text: str, lang: str, mode: str) -> str:
    if not oai_client:
        # Fallback без OpenAI
        if mode == "short":
            return "Кратко: запрос принят. Дайте 1–2 уточнения — отвечу конкретнее."
        if mode == "deep":
            return "Глубоко: распишу контекст и пошаговый план после уточнения цели и ограничений."
        return "Развёрнуто: дам ясный и полезный ответ по вашему запросу."
    # Подготовка сообщений
    style_hint = {
        "short":   "Формат: 3–5 пунктов с пользой.",
        "expanded":"Формат: 2–3 абзаца и список действий 5–7 шагов.",
        "deep":    "Формат: анализ, план 7–10 шагов, риски/метрики."
    }.get(mode, "Формат: 2–3 абзаца + действия.")
    system = system_prompt_for_lang(lang)
    messages = [
        {"role":"system","content": system + f"\nТекущий режим: {mode}. {style_hint}"},
        {"role":"user","content": user_text},
    ]
    # Вызов в отдельном потоке, чтобы не блокировать event loop
    def _call():
        return oai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.7,
        )
    resp = await asyncio.to_thread(_call)
    return (resp.choices[0].message.content or "").strip()

async def gpt_stories(topic: str, lang: str, mode: str) -> str:
    if not oai_client:
        # Простой fallback
        base = [
            f"Кадр 1 — Хук: {topic.capitalize()}",
            "Кадр 2 — Атмосфера: 3 детали сцены.",
            "Кадр 3 — Действие: шаг за 2–3 минуты.",
            "Кадр 4 — Ошибка: чего избежать.",
            "Кадр 5 — Чек‑лист: 4–5 пунктов.",
            "Кадр 6 — Микро‑история: 2–3 предложения.",
            "Кадр 7 — CTA: что написать дальше."
        ]
        n = {"short":4,"expanded":6,"deep":7}.get(mode,6)
        return "Готовые Stories:\n" + "\n".join("— "+x for x in base[:n])
    frames_hint = {
        "short":   "Сделай 4 кадра.",
        "expanded":"Сделай 6 кадров.",
        "deep":    "Сделай 7 кадров."
    }.get(mode, "Сделай 6 кадров.")
    prompt = (
        f"Сгенерируй Stories по теме: «{topic}». {frames_hint} "
        "Каждый кадр начинается с «— Кадр N — ...». Дай живые детали (звук/свет/движение), короткие фразы, чек‑лист и CTA в конце. "
        "Не повторяй мой текст и не добавляй префиксы «Вот...». "
    )
    system = system_prompt_for_lang(lang)
    def _call():
        return oai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
            temperature=0.8,
        )
    resp = await asyncio.to_thread(_call)
    return (resp.choices[0].message.content or "").strip()

# -------- Ютилиты --------
def want_stories(txt: str) -> bool:
    t = (txt or "").lower()
    return any(k in t for k in ["сторис", "stories", "story", "истории", "мпе", "мпэ"])

def extract_topic(txt: str) -> str:
    t = (txt or "").strip()
    m = re.search(r"(?:про|about)\s+(.+)$", t, re.IGNORECASE)
    return (m.group(1).strip() if m else "") or "тема"

def tts_make(text: str, lang: str):
    # По запросу из меню (не авто)
    tmp = tempfile.gettempdir()
    mp3 = os.path.join(tmp, f"{int(time.time()*1000)}.mp3")
    ogg = os.path.join(tmp, f"{int(time.time()*1000)+1}.ogg")
    try:
        gTTS(text=text, lang=lang if lang in ("ru","en","he") else "en").save(mp3)
        try:
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            subprocess.run([ffmpeg_path,"-y","-i",mp3,"-c:a","libopus","-b:a","48k","-ac","1","-ar","48000",ogg],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ("voice", ogg, mp3)
        except Exception:
            return ("audio", mp3, mp3)
    except Exception:
        return ("text", "", "")

# ======================= Команды =======================
@dp.message(Command("start"))
async def cmd_start(m: Message):
    ensure_profile(m.from_user.id)
    L = ui_lang[m.from_user.id]
    await m.answer(t_ui(L)["hello"])

@dp.message(Command("menu"))
async def cmd_menu(m: Message):
    ensure_profile(m.from_user.id)
    L = ui_lang[m.from_user.id]
    await m.answer(t_ui(L)["menu_title"], reply_markup=inline_main_menu(L))

@dp.message(Command("help"))
async def cmd_help(m: Message):
    ensure_profile(m.from_user.id)
    L = ui_lang[m.from_user.id]
    await m.answer("Как использовать:\n— Пишите текст/голос — отвечаю без повтора.\n— Действия — через /menu.\n— Команды: /start, /menu, /help, /version.")

@dp.message(Command("version"))
async def cmd_version(m: Message):
    await m.answer(VERSION)

# ======================= Inline‑меню =======================
@dp.callback_query(F.data == "m_close")
async def cb_close(cq: CallbackQuery):
    try:
        await cq.message.edit_text(" ")
    except Exception:
        pass
    await cq.answer()

@dp.callback_query(F.data == "m_help")
async def cb_help(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru")
    await cq.message.edit_text(
        "Помощь:\n— /menu открывает действия.\n— «Дай голосом» озвучит ответ.\n— «Показать расшифровку» — после подключения ASR.\n— «Сменить язык» — RU/EN/HE.\n— «Режим ответа» — Кратко/Развёрнуто/Глубоко.",
        reply_markup=inline_main_menu(L)
    ); await cq.answer()

@dp.callback_query(F.data == "m_pay")
async def cb_pay(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru")
    await cq.message.edit_text(t_ui(L)["pay_stub"], reply_markup=inline_main_menu(L)); await cq.answer()

@dp.callback_query(F.data == "m_refs")
async def cb_refs(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru")
    uname = BOT_USERNAME or "your_bot"
    link = f"https://t.me/{uname}?start=ref_{cq.from_user.id}"
    await cq.message.edit_text(t_ui(L)["refs_stub"].format(link=link), reply_markup=inline_main_menu(L)); await cq.answer()

@dp.callback_query(F.data == "m_profile")
async def cb_profile(cq: CallbackQuery):
    uid = cq.from_user.id; L = ui_lang.get(uid, "ru")
    mode = reply_mode.get(uid, "expanded"); cl = content_lang.get(uid, "ru")
    txt = t_ui(L)["profile_stub"].format(ui=L, mode=mode, cl=cl, ver=VERSION)
    await cq.message.edit_text(txt, reply_markup=inline_main_menu(L)); await cq.answer()

@dp.callback_query(F.data == "m_lang")
async def cb_lang(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru"); t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский", callback_data="ui_ru"),
         InlineKeyboardButton(text="English", callback_data="ui_en"),
         InlineKeyboardButton(text="עברית",  callback_data="ui_he")],
        [InlineKeyboardButton(text=t["close"], callback_data="m_close")]])
    await cq.message.edit_text(t["lang_choose"], reply_markup=kb); await cq.answer()

@dp.callback_query(F.data.in_({"ui_ru","ui_en","ui_he"}))
async def cb_set_lang(cq: CallbackQuery):
    mapping = {"ui_ru":"ru","ui_en":"en","ui_he":"he"}
    newL = mapping.get(cq.data, "ru")
    ui_lang[cq.from_user.id] = newL
    await cq.answer(t_ui(newL)["lang_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(newL)["lang_saved"], reply_markup=inline_main_menu(newL))

@dp.callback_query(F.data == "m_mode")
async def cb_mode(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru"); t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["mode_short"],    callback_data="rm_short"),
         InlineKeyboardButton(text=t["mode_expanded"], callback_data="rm_expanded"),
         InlineKeyboardButton(text=t["mode_deep"],     callback_data="rm_deep")],
        [InlineKeyboardButton(text=t["close"], callback_data="m_close")]])
    await cq.message.edit_text(t["mode_choose"], reply_markup=kb); await cq.answer()

@dp.callback_query(F.data.in_({"rm_short","rm_expanded","rm_deep"}))
async def cb_set_mode(cq: CallbackQuery):
    uid = cq.from_user.id; L = ui_lang.get(uid, "ru")
    reply_mode[uid] = {"rm_short":"short","rm_expanded":"expanded","rm_deep":"deep"}[cq.data]
    await cq.answer(t_ui(L)["mode_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(L)["mode_saved"], reply_markup=inline_main_menu(L))

# ----- TTS по запросу из меню -----
@dp.callback_query(F.data == "m_say")
async def cb_say(cq: CallbackQuery):
    uid = cq.from_user.id; ensure_profile(uid)
    L_ui = ui_lang[uid]; Lc = content_lang.get(uid, L_ui)
    mode = reply_mode.get(uid, "expanded")
    # Возьмем короткий GPT‑ответ и озвучим
    text = await gpt_answer("Сделай короткое полезное резюме по моему последнему запросу.", Lc, "short")
    kind, path, _ = tts_make(text, {"ru":"ru","en":"en","he":"he"}.get(Lc, "en"))
    if kind == "voice":
        await bot.send_voice(chat_id=cq.message.chat.id, voice=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
    elif kind == "audio":
        await bot.send_audio(chat_id=cq.message.chat.id, audio=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
    else:
        await bot.send_message(cq.message.chat.id, text)
    await cq.answer()

@dp.callback_query(F.data == "m_showtr")
async def cb_showtr(cq: CallbackQuery):
    uid = cq.from_user.id; L = ui_lang.get(uid, "ru")
    tr = _asr_store.get(uid, "")
    await bot.send_message(cq.message.chat.id, f"Расшифровка (по запросу):\n{tr}" if tr else t_ui(L)["no_transcript"])
    await cq.answer()

# ======================= Текст: Stories + GPT‑ответ =======================
@dp.message(F.text)
async def on_text(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    txt = (m.text or "").strip()

    # Stories
    if want_stories(txt):
        mode = reply_mode.get(m.from_user.id, "expanded")
        Lc   = content_lang.get(m.from_user.id, "ru")
        topic = extract_topic(txt)
        out = await gpt_stories(topic, Lc, mode)
        await m.answer(out)
        return

    # Ловушка «скрытого эха» 15 сек
    if time.time() - _last_voice_at.get(m.from_user.id, 0) <= 15:
        if _norm(txt) == _last_asr_text.get(m.from_user.id, ""):
            mode = reply_mode.get(m.from_user.id, "expanded")
            Lc   = content_lang.get(m.from_user.id, L_ui)
            safe = await _anti_echo_text(Lc, mode)
            await m.answer(safe)
            return

    # Автоязык контента (EN не по «коротышам» <12)
    cand = detect_script_lang(txt) or "en"
    if cand == "en" and len(txt) < 12:
        cand = content_lang.get(m.from_user.id, "ru")
    stable = update_content_lang(m.from_user.id, cand)

    # GPT‑ответ
    mode = reply_mode.get(m.from_user.id, "expanded")
    answer = await gpt_answer(txt, stable, mode)
    await m.answer(answer)

# ======================= Голос: анти‑эхо, без авто‑TTS =======================
@dp.message(F.voice)
async def on_voice(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    Lc   = content_lang.get(m.from_user.id, L_ui)
    mode = reply_mode.get(m.from_user.id, "expanded")

    # Пока ASR не подключён
    asr_text = ""
    _last_voice_at[m.from_user.id] = time.time()
    if asr_text:
        _asr_store[m.from_user.id] = asr_text
        _last_asr_text[m.from_user.id] = _norm(asr_text)
    else:
        _asr_store.pop(m.from_user.id, None)
        _last_asr_text.pop(m.from_user.id, None)

    text = await _anti_echo_text(Lc, mode)
    await m.answer(text)
    await m.answer(t_ui(L_ui)["voice_hint"])

# ======================= Фото/Видео: безопасные карточки =======================
@dp.message(F.photo)
async def on_photo(m: Message):
    await m.answer("Фото получено. OCR/Vision пока отключены — ничего не угадываю. После подключения «Расшифровка (OCR)» будет доступна через /menu.")

@dp.message(F.video | F.video_note)
async def on_video(m: Message):
    await m.answer("Видео получено. Транскрипт/таймкоды подключим позже. Нужны действия — откройте /menu.")

# ======================= FastAPI: health + version + webhook =======================
@app.get("/")
async def root_ok():
    return Response(content="OK", media_type="text/plain")

@app.get("/version")
async def http_version():
    return Response(content=VERSION, media_type="text/plain")

@app.get(f"/telegram/{SECRET}")
async def webhook_ok():
    return Response(content="Webhook OK", media_type="text/plain")

@app.post(f"/telegram/{SECRET}")
async def telegram_webhook(req: Request):
    data = await req.json()
    try:
        update = Update.model_validate(data)
    except Exception:
        return Response(status_code=200)
    await dp.feed_update(bot=bot, update=update)
    return Response(status_code=200)

@app.on_event("startup")
async def on_startup():
    global BOT_USERNAME
    print(VERSION)
    try:
        me = await bot.get_me()
        BOT_USERNAME = me.username or ""
    except Exception:
        BOT_USERNAME = ""
    if BASE:
        try:
            await bot.set_webhook(f"{BASE}/telegram/{SECRET}")
        except Exception as e:
            print("set_webhook error:", e)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
