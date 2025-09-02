# SmartPro 24/7 — ANTI-ECHO HOTFIX#2 (2025-09-02)
# Голос: без повтора, без авто‑TTS, без кнопки расшифровки, пока ASR не подключён.
# Меню: постоянная клавиатура, /start /menu /help /version.

import os, re, time
from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, Update, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

# ====== Конфигурация окружения (поддержка старых имён переменных) ======
TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
SECRET = os.getenv("WEBHOOK_SECRET") or os.getenv("TELEGRAM_WEBHOOK_SECRET", "railway123")
BASE   = os.getenv("BASE_URL") or os.getenv("PUBLIC_BASE_URL", "")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

bot = Bot(TOKEN)
dp  = Dispatcher()
app = FastAPI()

VERSION = "ANTI-ECHO v2025-09-02 HOTFIX#2"

# ====== Сессия пользователя (in‑mem) ======
ui_lang: dict[int, str] = {}
reply_mode: dict[int, str] = {}
last_content_langs: dict[int, list[str]] = {}
content_lang: dict[int, str] = {}
_asr_store: dict[int, str] = {}
_last_voice_at: dict[int, float] = {}
_last_asr_text: dict[int, str] = {}

# ====== Локализация UI ======
def t_ui(lang: str = "ru"):
    data = {
        "ru": dict(
            ready="Готов. Выберите действие:",
            say="Дай голосом",
            show_tr="Показать расшифровку",
            lang="Сменить язык",
            mode="Режим ответа",
            mode_choose="Выберите стиль ответа:",
            mode_saved="Режим ответа сохранён.",
            mode_short="Кратко",
            mode_expanded="Развёрнуто",
            mode_deep="Глубоко",
            lang_choose="Выберите язык интерфейса:",
            lang_saved="Язык интерфейса сохранён.",
            menu_hint="Если клавиатура пропала — нажмите /menu",
        ),
        "en": dict(
            ready="Ready. Choose an action:",
            say="Speak it",
            show_tr="Show transcript",
            lang="Change language",
            mode="Reply mode",
            mode_choose="Choose reply style:",
            mode_saved="Reply mode saved.",
            mode_short="Short",
            mode_expanded="Expanded",
            mode_deep="In‑depth",
            lang_choose="Choose interface language:",
            lang_saved="Interface language saved.",
            menu_hint="If the keyboard disappeared — press /menu",
        ),
        "he": dict(
            ready="מוכן. בחרו פעולה:",
            say="השמע בקול",
            show_tr="הצג תמלול",
            lang="החלפת שפה",
            mode="מצב תגובה",
            mode_choose="בחרו סגנון תשובה:",
            mode_saved="מצב התגובה נשמר.",
            mode_short="קצר",
            mode_expanded="מורחב",
            mode_deep="מעמיק",
            lang_choose="בחרו שפת ממשק:",
            lang_saved="שפת הממשק נשמרה.",
            menu_hint="אם המקלדת נעלמה — לחצו /menu",
        ),
    }
    return data.get(lang, data["ru"])

def main_kb(lang: str = "ru"):
    t = t_ui(lang)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["say"]),  KeyboardButton(text=t["show_tr"])],
            [KeyboardButton(text=t["lang"]), KeyboardButton(text=t["mode"])],
        ],
        resize_keyboard=True,
        is_persistent=True,
        one_time_keyboard=False,
    )

# ====== Автоязык контента + гистерезис ======
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
    if len(arr) > 3:
        arr.pop(0)
    last_content_langs[uid] = arr
    counts = {}
    for c in arr:
        counts[c] = counts.get(c, 0) + 1
    best, mx = None, 0
    for k, v in counts.items():
        if v > mx:
            best, mx = k, v
    if mx >= 2:
        content_lang[uid] = best
    return content_lang.get(uid, candidate)

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().casefold()

# ====== Профиль и базовые ответы ======
def ensure_profile(uid: int):
    if uid not in ui_lang:    ui_lang[uid] = "ru"
    if uid not in reply_mode: reply_mode[uid] = "expanded"

def compose_reply(lang: str, mode: str) -> str:
    if mode not in ("short","expanded","deep"):
        mode = "expanded"
    if lang == "he":
        base = {"short":"תקציר: קיבלתי. קצר.",
                "expanded":"תקציר: תשובה מועילה וברורה.",
                "deep":"מעמיק: הקשר ושלבים מפורטים."}
    elif lang == "en":
        base = {"short":"Summary: received. Brief.",
                "expanded":"Summary: clear and useful answer.",
                "deep":"In‑depth: context and steps."}
    else:
        base = {"short":"Кратко: запрос принят.",
                "expanded":"Развёрнуто: дам ясный и полезный ответ.",
                "deep":"Глубоко: контекст и пошаговые действия."}
    return base[mode]

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

# ====== Команды ======
@dp.message(Command("start"))
async def on_start(m: Message):
    ensure_profile(m.from_user.id)
    L = ui_lang[m.from_user.id]
    await m.answer(f"Старт. {t_ui(L)['menu_hint']}", reply_markup=main_kb(L))
    await m.answer(t_ui(L)["ready"], reply_markup=main_kb(L))

@dp.message(Command("menu"))
async def on_menu(m: Message):
    ensure_profile(m.from_user.id)
    L = ui_lang[m.from_user.id]
    await m.answer(t_ui(L)["ready"], reply_markup=main_kb(L))

@dp.message(Command("help"))
async def on_help(m: Message):
    ensure_profile(m.from_user.id)
    L = ui_lang[m.from_user.id]
    await m.answer(
        "Доступно: /start, /menu, /help, /version\n"
        "Кнопки: «Дай голосом», «Показать расшифровку», «Сменить язык», «Режим ответа».\n"
        "Голос: распознавание временно отключено; без повтора текста.\n",
        reply_markup=main_kb(L)
    )

@dp.message(Command("version"))
async def on_version(m: Message):
    await m.answer(VERSION, reply_markup=main_kb(ui_lang.get(m.from_user.id, "ru")))

# ====== Смена языка и режима ======
@dp.message(F.text.in_([t_ui("ru")["lang"], t_ui("en")["lang"], t_ui("he")["lang"]]))
async def ask_lang(m: Message):
    L = ui_lang.get(m.from_user.id, "ru"); t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский", callback_data="ui_ru"),
         InlineKeyboardButton(text="English", callback_data="ui_en")],
        [InlineKeyboardButton(text="עברית",  callback_data="ui_he")]
    ])
    await m.answer(t["lang_choose"], reply_markup=kb)

@dp.callback_query(F.data.in_({"ui_ru","ui_en","ui_he"}))
async def on_ui_change(cq: CallbackQuery):
    mapping = {"ui_ru":"ru","ui_en":"en","ui_he":"he"}
    newL = mapping.get(cq.data, "ru")
    ui_lang[cq.from_user.id] = newL
    await cq.answer(t_ui(newL)["lang_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(newL)["lang_saved"])
    await bot.send_message(cq.message.chat.id, t_ui(newL)["ready"], reply_markup=main_kb(newL))

@dp.message(F.text.in_([t_ui("ru")["mode"], t_ui("en")["mode"], t_ui("he")["mode"]]))
async def ask_mode(m: Message):
    L = ui_lang.get(m.from_user.id, "ru"); t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["mode_short"],    callback_data="rm_short"),
         InlineKeyboardButton(text=t["mode_expanded"], callback_data="rm_expanded"),
         InlineKeyboardButton(text=t["mode_deep"],     callback_data="rm_deep")]
    ])
    await m.answer(t["mode_choose"], reply_markup=kb)

@dp.callback_query(F.data.in_({"rm_short","rm_expanded","rm_deep"}))
async def on_mode_change(cq: CallbackQuery):
    uid = cq.from_user.id; L = ui_lang.get(uid, "ru")
    reply_mode[uid] = {"rm_short":"short","rm_expanded":"expanded","rm_deep":"deep"}[cq.data]
    await cq.answer(t_ui(L)["mode_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(L)["mode_saved"])
    await bot.send_message(cq.message.chat.id, t_ui(L)["ready"], reply_markup=main_kb(L))

# ====== Показ расшифровки (кнопка клавиатуры) ======
@dp.message(F.text.in_([t_ui("ru")["show_tr"], t_ui("en")["show_tr"], t_ui("he")["show_tr"]]))
async def on_show_tr_btn(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang.get(m.from_user.id, "ru")
    tr = _asr_store.get(m.from_user.id, "")
    if tr:
        await m.answer(f"Расшифровка (по запросу):\n{tr}", reply_markup=main_kb(L_ui))
    else:
        await m.answer("Расшифровка пока недоступна (распознавание временно отключено).", reply_markup=main_kb(L_ui))

# ====== Текст: автоязык + ловушка «скрытого эха» ======
@dp.message(F.text)
async def on_text(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    txt = (m.text or "").strip()

    # ловушка «скрытого эха» 15 сек
    if time.time() - _last_voice_at.get(m.from_user.id, 0) <= 15:
        if _norm(txt) == _last_asr_text.get(m.from_user.id, ""):
            mode = reply_mode.get(m.from_user.id, "expanded")
            Lc   = content_lang.get(m.from_user.id, L_ui)
            await m.answer(compose_reply(Lc, mode), reply_markup=main_kb(L_ui))
            return

    # автоязык (EN не по коротышам <12)
    cand = detect_script_lang(txt) or "en"
    if cand == "en" and len(txt) < 12:
        cand = content_lang.get(m.from_user.id, "ru")
    stable = update_content_lang(m.from_user.id, cand)

    mode = reply_mode.get(m.from_user.id, "expanded")
    await m.answer(compose_reply(stable, mode), reply_markup=main_kb(L_ui))

# ====== ВОЙС: анти‑эхо, БЕЗ авто‑озвучки и БЕЗ инлайн‑кнопки ======
@dp.message(F.voice)
async def on_voice(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    Lc   = content_lang.get(m.from_user.id, L_ui)
    mode = reply_mode.get(m.from_user.id, "expanded")

    # Пока ASR не подключён — храним пусто
    asr_text = ""  # TODO: вставим реальный ASR позже
    _last_voice_at[m.from_user.id] = time.time()
    if asr_text:
        _asr_store[m.from_user.id] = asr_text
        _last_asr_text[m.from_user.id] = _norm(asr_text)
    else:
        _asr_store.pop(m.from_user.id, None)
        _last_asr_text.pop(m.from_user.id, None)

    # Структурный ответ без повтора
    text = await _anti_echo_text(Lc, mode)
    await m.answer(text, reply_markup=main_kb(L_ui))
    # Ясное пояснение вместо «Озвучено …»
    await m.answer("Голос получен. Распознавание временно отключено — напишите текстом или используйте кнопки.", reply_markup=main_kb(L_ui))

# ====== Фото/Видео: безопасные карточки ======
@dp.message(F.photo)
async def on_photo(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    await m.answer(
        "Фото получено.\n"
        "— OCR/Vision временно отключены — ничего не угадываю.\n"
        "— После подключения появится «Расшифровка (OCR)».",
        reply_markup=main_kb(L_ui)
    )

@dp.message(F.video | F.video_note)
async def on_video(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    await m.answer(
        "Видео получено.\n"
        "— Транскрипт и таймкоды подключим позже.\n"
        "— Могу выдать структуру/чек‑лист по запросу.",
        reply_markup=main_kb(L_ui)
    )

# ====== FastAPI: health + webhook ======
@app.get("/")
async def root_ok():
    return Response(content="OK", media_type="text/plain")

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
    print(VERSION)
    if BASE:
        try:
            await bot.set_webhook(f"{BASE}/telegram/{SECRET}")
        except Exception as e:
            print("set_webhook error:", e)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
