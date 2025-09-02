# SmartPro 24/7 — ANTI‑ECHO HOTFIX#5 (Greeting + Full Inline Menu on /menu only)
# UX:
# - /start: Чёткое приветствие (ничего не раскрываем).
# - /menu: Открывает ПОЛНОЕ inline‑меню: Помощь • Оплатить • Рефералы • Профиль • Сменить язык • Режим ответа • Дай голосом • Показать расшифровку • Скрыть.
# - Нет принудительной нижней клавиатуры. Все действия — через /menu (inline‑кнопки).
# Голос:
# - Никогда не повторяем распознанный текст; авто‑TTS на войс отключён.
# - «Показать расшифровку» покажет текст только после подключения ASR (пока заглушка).

import os, re, time, tempfile, subprocess
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

# ---------- Конфигурация окружения (поддержка старых имён переменных) ----------
TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
SECRET = os.getenv("WEBHOOK_SECRET") or os.getenv("TELEGRAM_WEBHOOK_SECRET", "railway123")
BASE   = os.getenv("BASE_URL") or os.getenv("PUBLIC_BASE_URL", "")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

bot = Bot(TOKEN)
dp  = Dispatcher()
app = FastAPI()

VERSION = "ANTI‑ECHO v2025‑09‑02 HOTFIX#5"
BOT_USERNAME = ""

# ---------- Память сессии (in‑memory) ----------
ui_lang: dict[int, str] = {}                 # RU/EN/HE
reply_mode: dict[int, str] = {}              # short/expanded/deep
last_content_langs: dict[int, list[str]] = {}
content_lang: dict[int, str] = {}
_asr_store: dict[int, str] = {}
_last_voice_at: dict[int, float] = {}
_last_asr_text: dict[int, str] = {}

# ---------- Локализация ----------
def t_ui(lang: str = "ru"):
    data = {
        "ru": dict(
            hello=(
                "Привет! Я SmartPro 24/7 — универсальный помощник для текста, голоса и медиа.\n"
                "Помогу: быстрое резюме, разбор, идеи, сторис, карточки фото/видео.\n"
                "Чтобы открыть действия — используйте /menu."
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
            pay_stub="Оплата скоро: Stripe Checkout (USD $10 / $20 / $50). Включим после UAT.",
            refs_stub="Ваша реф‑ссылка:\n{link}\nБонус: +3 за каждого платящего друга.",
            profile_stub="Профиль:\n— UI язык: {ui}\n— Режим ответа: {mode}\n— Язык контента: {cl}\n— Версия: {ver}",
            no_transcript="Расшифровка пока недоступна (ASR отключён).",
            voice_hint="Голос получен. Распознавание временно отключено — отвечаю без повтора. Нужны действия? Откройте /menu.",
        ),
        "en": dict(
            hello=(
                "Hi! I’m SmartPro 24/7 — a universal assistant for text, voice and media.\n"
                "I help with summaries, deep dives, ideas, stories, and media cards.\n"
                "Open actions via /menu."
            ),
            menu_title="Actions menu",
            help="Help",
            pay="Pay",
            refs="Referrals",
            profile="Profile",
            lang="Change language",
            mode="Reply mode",
            say="Speak it",
            show_tr="Show transcript",
            close="Hide",
            mode_choose="Choose reply style:",
            mode_saved="Reply mode saved.",
            mode_short="Short",
            mode_expanded="Expanded",
            mode_deep="In‑depth",
            lang_choose="Choose interface language:",
            lang_saved="Interface language saved.",
            tts_caption="Voiced",
            pay_stub="Payments soon: Stripe Checkout (USD $10 / $20 / $50). Will enable after UAT.",
            refs_stub="Your referral link:\n{link}\nBonus: +3 for each paying friend.",
            profile_stub="Profile:\n— UI lang: {ui}\n— Reply mode: {mode}\n— Content lang: {cl}\n— Version: {ver}",
            no_transcript="Transcript is not available yet (ASR disabled).",
            voice_hint="Voice received. ASR is disabled for now — replying without echo. Need actions? Open /menu.",
        ),
        "he": dict(
            hello="שלום! אני SmartPro 24/7. השתמשו ב‑/menu כדי לפתוח את תפריט הפעולות.",
            menu_title="תפריט פעולות",
            help="עזרה",
            pay="לתשלום",
            refs="הפניות",
            profile="פרופיל",
            lang="החלפת שפה",
            mode="מצב תגובה",
            say="השמע בקול",
            show_tr="הצג תמלול",
            close="סגור",
            mode_choose="בחרו סגנון תשובה:",
            mode_saved="מצב התגובה נשמר.",
            mode_short="קצר",
            mode_expanded="מורחב",
            mode_deep="מעמיק",
            lang_choose="בחרו שפת ממשק:",
            lang_saved="שפת הממשק נשמרה.",
            tts_caption="הוקרא",
            pay_stub="תשלומים בקרוב: Stripe (USD $10 / $20 / $50). נאפשר לאחר UAT.",
            refs_stub="קישור ההפניה שלך:\n{link}\nבונוס: +3 על כל חבר משלם.",
            profile_stub="פרופיל:\n— שפת UI: {ui}\n— מצב תגובה: {mode}\n— שפת תוכן: {cl}\n— גרסה: {ver}",
            no_transcript="אין עדיין תמלול (ASR כבוי).",
            voice_hint="הודעה קולית התקבלה. ASR כבוי — עונה ללא הדהוד. פעולות? פתחו /menu.",
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

# ---------- Автоязык контента + гистерезис ----------
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

def compose_reply(lang: str, mode: str) -> str:
    if mode not in ("short","expanded","deep"): mode = "expanded"
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
    if mode not in ("short","expanded","deep"): mode = "expanded"
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

# ---------- Команды ----------
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
    await m.answer(
        "Как использовать:\n"
        "— Пишите текст или отправляйте голос — отвечу без повтора речи.\n"
        "— Для действий откройте /menu (Оплата, Рефералы, Профиль, Язык, Режим ответа, Озвучка, Расшифровка).\n"
        "— Команды: /start, /menu, /help, /version."
    )

@dp.message(Command("version"))
async def cmd_version(m: Message):
    await m.answer(VERSION)

# ---------- Обработчики inline‑меню ----------
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
        "Помощь:\n"
        "— /menu открывает действия.\n"
        "— «Дай голосом» озвучит мой ответ.\n"
        "— «Показать расшифровку» — после подключения ASR.\n"
        "— «Сменить язык» — RU/EN/HE.\n"
        "— «Режим ответа» — Кратко/Развёрнуто/Глубоко.",
        reply_markup=inline_main_menu(L)
    )
    await cq.answer()

@dp.callback_query(F.data == "m_pay")
async def cb_pay(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru")
    await cq.message.edit_text(t_ui(L)["pay_stub"], reply_markup=inline_main_menu(L))
    await cq.answer()

@dp.callback_query(F.data == "m_refs")
async def cb_refs(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru")
    uname = BOT_USERNAME or "your_bot"
    link = f"https://t.me/{uname}?start=ref_{cq.from_user.id}"
    await cq.message.edit_text(t_ui(L)["refs_stub"].format(link=link), reply_markup=inline_main_menu(L))
    await cq.answer()

@dp.callback_query(F.data == "m_profile")
async def cb_profile(cq: CallbackQuery):
    uid = cq.from_user.id
    L = ui_lang.get(uid, "ru")
    mode = reply_mode.get(uid, "expanded")
    cl = content_lang.get(uid, "ru")
    txt = t_ui(L)["profile_stub"].format(ui=L, mode=mode, cl=cl, ver=VERSION)
    await cq.message.edit_text(txt, reply_markup=inline_main_menu(L))
    await cq.answer()

@dp.callback_query(F.data == "m_lang")
async def cb_lang(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru")
    t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский", callback_data="ui_ru"),
         InlineKeyboardButton(text="English", callback_data="ui_en"),
         InlineKeyboardButton(text="עברית",  callback_data="ui_he")],
        [InlineKeyboardButton(text=t["close"], callback_data="m_close")]
    ])
    await cq.message.edit_text(t["lang_choose"], reply_markup=kb)
    await cq.answer()

@dp.callback_query(F.data.in_({"ui_ru","ui_en","ui_he"}))
async def cb_set_lang(cq: CallbackQuery):
    mapping = {"ui_ru":"ru","ui_en":"en","ui_he":"he"}
    newL = mapping.get(cq.data, "ru")
    ui_lang[cq.from_user.id] = newL
    await cq.answer(t_ui(newL)["lang_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(newL)["lang_saved"], reply_markup=inline_main_menu(newL))

@dp.callback_query(F.data == "m_mode")
async def cb_mode(cq: CallbackQuery):
    L = ui_lang.get(cq.from_user.id, "ru")
    t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["mode_short"],    callback_data="rm_short"),
         InlineKeyboardButton(text=t["mode_expanded"], callback_data="rm_expanded"),
         InlineKeyboardButton(text=t["mode_deep"],     callback_data="rm_deep")],
        [InlineKeyboardButton(text=t["close"], callback_data="m_close")]
    ])
    await cq.message.edit_text(t["mode_choose"], reply_markup=kb)
    await cq.answer()

@dp.callback_query(F.data.in_({"rm_short","rm_expanded","rm_deep"}))
async def cb_set_mode(cq: CallbackQuery):
    uid = cq.from_user.id
    L = ui_lang.get(uid, "ru")
    reply_mode[uid] = {"rm_short":"short","rm_expanded":"expanded","rm_deep":"deep"}[cq.data]
    await cq.answer(t_ui(L)["mode_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(L)["mode_saved"], reply_markup=inline_main_menu(L))

# TTS по запросу «Дай голосом» (через меню)
def tts_make(text: str, lang: str):
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

@dp.callback_query(F.data == "m_say")
async def cb_say(cq: CallbackQuery):
    uid = cq.from_user.id
    ensure_profile(uid)
    L_ui = ui_lang[uid]
    Lc   = content_lang.get(uid, L_ui)
    mode = reply_mode.get(uid, "expanded")
    text = compose_reply(Lc, mode)
    kind, path, _ = tts_make(text, {"ru":"ru","en":"en","he":"he"}.get(Lc,"en"))
    if kind == "voice":
        await bot.send_voice(chat_id=cq.message.chat.id, voice=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
    elif kind == "audio":
        await bot.send_audio(chat_id=cq.message.chat.id, audio=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
    else:
        await bot.send_message(cq.message.chat.id, text)
    await cq.answer()

@dp.callback_query(F.data == "m_showtr")
async def cb_showtr(cq: CallbackQuery):
    uid = cq.from_user.id
    L = ui_lang.get(uid, "ru")
    tr = _asr_store.get(uid, "")
    if tr:
        await bot.send_message(cq.message.chat.id, f"Расшифровка (по запросу):\n{tr}")
    else:
        await bot.send_message(cq.message.chat.id, t_ui(L)["no_transcript"])
    await cq.answer()

# ---------- Текст: автоязык + ловушка «скрытого эха» ----------
@dp.message(F.text)
async def on_text(m: Message):
    ensure_profile(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    txt = (m.text or "").strip()

    # 15‑сек ловушка «скрытого эха»
    if time.time() - _last_voice_at.get(m.from_user.id, 0) <= 15:
        if _norm(txt) == _last_asr_text.get(m.from_user.id, ""):
            mode = reply_mode.get(m.from_user.id, "expanded")
            Lc   = content_lang.get(m.from_user.id, L_ui)
            await m.answer(compose_reply(Lc, mode))
            return

    # автоязык (EN не переключаем по «коротышам» <12)
    cand = detect_script_lang(txt) or "en"
    if cand == "en" and len(txt) < 12:
        cand = content_lang.get(m.from_user.id, "ru")
    stable = update_content_lang(m.from_user.id, cand)

    mode = reply_mode.get(m.from_user.id, "expanded")
    await m.answer(compose_reply(stable, mode))

# ---------- Голос: анти‑эхо, БЕЗ авто‑TTS ----------
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

# ---------- Фото/Видео: безопасные карточки ----------
@dp.message(F.photo)
async def on_photo(m: Message):
    await m.answer("Фото получено. OCR/Vision пока отключены — ничего не угадываю. После подключения «Расшифровка (OCR)» будет доступна через /menu.")

@dp.message(F.video | F.video_note)
async def on_video(m: Message):
    await m.answer("Видео получено. Транскрипт/таймкоды подключим позже. Нужны действия — откройте /menu.")

# ---------- FastAPI: health + webhook ----------
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
