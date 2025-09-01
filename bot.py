from fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, Update,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from gtts import gTTS
import imageio_ffmpeg
import os, re, tempfile, time, subprocess, uuid, asyncio, mimetypes
from pathlib import Path

# ------------- Конфигурация -------------
TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
SECRET = os.getenv("WEBHOOK_SECRET", "railway123")     # должен совпасть с URL
BASE   = os.getenv("BASE_URL", "")                     # напр.: https://universal-bot-production.up.railway.app
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

bot = Bot(TOKEN)
dp  = Dispatcher()
app = FastAPI()

# ------------- Память пользователя (in‑mem) -------------
ui_lang: dict[int, str] = {}                 # язык интерфейса (ru|en|he) — фиксируется кнопкой
last_content_langs: dict[int, list[str]] = {}# последние 3 детекции языка контента
content_lang: dict[int, str] = {}            # стабильный язык контента
_asr_store: dict[int, str] = {}              # последняя расшифровка войса (по кнопке)
reply_mode: dict[int, str] = {}              # 'short' | 'expanded' | 'deep' (по умолчанию 'expanded')

# ------------- Локализация интерфейса -------------
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
            tts_caption="Озвучено",
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
            tts_caption="Voiced",
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
            tts_caption="הוקרא",
            menu_hint="אם המקלדת נעלמה — לחצו /menu",
        ),
    }
    return data.get(lang, data["ru"])

def main_kb(lang: str = "ru"):
    t = t_ui(lang)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["say"]), KeyboardButton(text=t["show_tr"])],
            [KeyboardButton(text=t["lang"]), KeyboardButton(text=t["mode"])]
        ],
        resize_keyboard=True
    )

# ------------- Детект языка контента (стабильный) -------------
rx = {
    "ru": re.compile(r"[А-Яа-яЁё]"), "he": re.compile(r"[א-ת]"),
    "ar": re.compile(r"[\u0600-\u06FF]"), "ja": re.compile(r"[\u3040-\u30FF\u4E00-\u9FFF]"),
    "ko": re.compile(r"[\uAC00-\uD7AF]"), "zh": re.compile(r"[\u4E00-\u9FFF]"),
    "en": re.compile(r"[A-Za-z]")
}
def detect_script_lang(text: str) -> str | None:
    for code, pat in rx.items():
        if pat.search(text or ""):
            return code
    return None

def update_content_lang(user_id: int, candidate: str) -> str:
    arr = last_content_langs.get(user_id, [])
    arr.append(candidate)
    if len(arr) > 3:
        arr.pop(0)
    last_content_langs[user_id] = arr
    counts: dict[str, int] = {}
    for c in arr:
        counts[c] = counts.get(c, 0) + 1
    best, mx = None, 0
    for k, v in counts.items():
        if v > mx:
            best, mx = k, v
    if mx >= 2:
        content_lang[user_id] = best
    return content_lang.get(user_id, candidate)

# ------------- TTS (OGG/Opus с imageio‑ffmpeg; fallback MP3) -------------
def tts_make(text: str, lang: str):
    tmp = tempfile.gettempdir()
    mp3 = os.path.join(tmp, f"{int(time.time()*1000)}.mp3")
    ogg = os.path.join(tmp, f"{int(time.time()*1000)+1}.ogg")

    tries = ["en", "ru"]
    if lang == "he": tries = ["he", "iw"] + tries
    elif lang == "zh": tries = ["zh-CN", "zh-TW"] + tries
    else: tries = [lang] + tries

    last_err = None
    for L in tries:
        try:
            gTTS(text=text, lang=L).save(mp3)
            try:
                ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run(
                    [ffmpeg_path, "-y", "-i", mp3, "-c:a", "libopus", "-b:a", "48k", "-ac", "1", "-ar", "48000", ogg],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return ("voice", ogg, mp3)
            except Exception:
                return ("audio", mp3, mp3)
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("TTS failed")

# ------------- Утилиты -------------
def ensure_profiles(uid: int):
    if uid not in ui_lang: ui_lang[uid] = "ru"
    if uid not in reply_mode: reply_mode[uid] = "expanded"

async def resend_menu(chat_id: int):
    L = ui_lang.get(chat_id, "ru")
    await bot.send_message(chat_id, t_ui(L)["ready"], reply_markup=main_kb(L))

# ------------- Генерация ответов по режиму -------------
def compose_reply(lang: str, mode: str) -> str:
    if mode not in ("short","expanded","deep"): mode = "expanded"
    if lang == "he":
        base = {"short":"תקציר: קיבלתי. קצר.", "expanded":"תקציר: קיבלתי. תשובה מועילה.", "deep":"מעמיק: הקשר ושלבים."}
    elif lang == "en":
        base = {"short":"Summary: received. Brief.", "expanded":"Summary: received. Useful details.", "deep":"In‑depth: context and steps."}
    else:
        base = {"short":"Кратко: запрос принят.", "expanded":"Развёрнуто: дам полезные детали.", "deep":"Глубоко: контекст и шаги."}
    return base[mode]

def tts_caption_for_mode(lang: str, mode: str) -> str:
    t = t_ui(lang)
    m = {"short":"Кратко","expanded":"Развёрнуто","deep":"Глубоко"}
    return f'{t["tts_caption"]} · {m.get(mode, "Развёрнуто")}'

# ------------- Хендлеры: базовые /start /menu /help -------------
@dp.message(Command("start"))
async def on_start(m: Message):
    ensure_profiles(m.from_user.id)
    L = ui_lang[m.from_user.id]
    # Покажем меню всегда
    await m.answer("Старт. " + t_ui(L)["menu_hint"], reply_markup=main_kb(L))
    await m.answer(t_ui(L)["ready"])

@dp.message(Command("menu"))
async def on_menu(m: Message):
    ensure_profiles(m.from_user.id)
    await resend_menu(m.chat.id)

@dp.message(Command("help"))
async def on_help(m: Message):
    ensure_profiles(m.from_user.id)
    L = ui_lang[m.from_user.id]
    txt = (
        "Доступно: /start, /menu, /help\n"
        "Кнопки: «Дай голосом», «Показать расшифровку», «Сменить язык», «Режим ответа».\n"
        "Стиль ответа: «Кратко/Развёрнуто/Глубоко» через «Режим ответа»."
    )
    await m.answer(txt, reply_markup=main_kb(L))

# ------------- Смена языка интерфейса и режима ответа -------------
@dp.message(F.text.in_([t_ui("ru")["lang"], t_ui("en")["lang"], t_ui("he")["lang"]]))
async def ask_lang(m: Message):
    L = ui_lang.get(m.from_user.id, "ru")
    t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Русский", callback_data="ui_ru"),
         InlineKeyboardButton(text="English", callback_data="ui_en")],
        [InlineKeyboardButton(text="עברית", callback_data="ui_he")]
    ])
    await m.answer(t["lang_choose"], reply_markup=kb)

@dp.callback_query(F.data.in_({"ui_ru","ui_en","ui_he"}))
async def on_ui_change(cq):
    mapping = {"ui_ru":"ru","ui_en":"en","ui_he":"he"}
    newL = mapping.get(cq.data, "ru")
    ui_lang[cq.from_user.id] = newL
    await cq.answer(t_ui(newL)["lang_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(newL)["lang_saved"])
    await resend_menu(cq.message.chat.id)

@dp.message(F.text.in_([t_ui("ru")["mode"], t_ui("en")["mode"], t_ui("he")["mode"]]))
async def ask_mode(m: Message):
    L = ui_lang.get(m.from_user.id, "ru")
    t = t_ui(L)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["mode_short"], callback_data="rm_short"),
         InlineKeyboardButton(text=t["mode_expanded"], callback_data="rm_expanded"),
         InlineKeyboardButton(text=t["mode_deep"], callback_data="rm_deep")]
    ])
    await m.answer(t["mode_choose"], reply_markup=kb)

@dp.callback_query(F.data.in_({"rm_short","rm_expanded","rm_deep"}))
async def on_mode_change(cq):
    uid = cq.from_user.id
    L = ui_lang.get(uid, "ru")
    reply_mode[uid] = {"rm_short":"short","rm_expanded":"expanded","rm_deep":"deep"}[cq.data]
    await cq.answer(t_ui(L)["mode_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(L)["mode_saved"])
    await resend_menu(cq.message.chat.id)

# ------------- «Дай голосом» -------------
@dp.message(F.text.in_([t_ui("ru")["say"], t_ui("en")["say"], t_ui("he")["say"]]))
async def on_tts_button(m: Message):
    ensure_profiles(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    Lc   = content_lang.get(m.from_user.id, "ru")
    mode = reply_mode.get(m.from_user.id, "expanded")
    text = compose_reply(Lc, mode)
    kind, path, _ = tts_make(text, Lc)
    if kind == "voice":
        await m.answer_voice(voice=FSInputFile(path), caption=tts_caption_for_mode(L_ui, mode))
    else:
        await m.answer_audio(audio=FSInputFile(path), caption=tts_caption_for_mode(L_ui, mode))

# ------------- Текст: автоязык контента (без «скачков») -------------
@dp.message(F.text)
async def on_text(m: Message):
    ensure_profiles(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    txt = (m.text or "").strip()
    cand = detect_script_lang(txt) or "en"
    if cand == "en" and len(txt) < 12:
        cand = content_lang.get(m.from_user.id, "ru")
    stable = update_content_lang(m.from_user.id, cand)
    mode = reply_mode.get(m.from_user.id, "expanded")
    await m.answer(compose_reply(stable, mode), reply_markup=main_kb(L_ui))

# ------------- ВОЙС: анти‑эхо + расшифровка по кнопке -------------
async def _summarize_without_echo(lang: str, mode: str) -> str:
    if lang == "he":
        base = {"short":"תקציר: קיבלתי. בלי הדהוד.",
                "expanded":"תקציר: תשובה עניינית ללא הדהוד.",
                "deep":"מעמיק: תשובה עם הקשר וצעד הבא — ללא הדהוד."}
        return base[mode]
    if lang == "en":
        base = {"short":"Summary: received. No echo.",
                "expanded":"Summary: to the point, no echo.",
                "deep":"In‑depth: context and next steps — without echo."}
        return base[mode]
    base = {"short":"Кратко: запрос принят. Без повтора слов.",
            "expanded":"Развёрнуто: по сути, не повторяя ваш текст.",
            "deep":"Глубоко: контекст и шаги — без повтора речи."}
    return base[mode]

@dp.message(F.voice)
async def on_voice(m: Message):
    ensure_profiles(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    Lc   = content_lang.get(m.from_user.id, L_ui)
    mode = reply_mode.get(m.from_user.id, "expanded")

    # Подключите ваш ASR здесь; по умолчанию не используем текст
    asr_text = ""
    _asr_store[m.from_user.id] = asr_text

    text = await _summarize_without_echo(Lc, mode)
    await m.answer(text, reply_markup=main_kb(L_ui))
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t_ui(L_ui)["show_tr"], callback_data="show_asr")]
    ])
    await m.answer("Готов показать расшифровку по кнопке:", reply_markup=kb)

    try:
        kind, path, _ = tts_make(text, Lc)
        if kind == "voice":
            await m.answer_voice(voice=FSInputFile(path), caption=tts_caption_for_mode(L_ui, mode))
        else:
            await m.answer_audio(audio=FSInputFile(path), caption=tts_caption_for_mode(L_ui, mode))
    except Exception:
        pass

@dp.callback_query(F.data == "show_asr")
async def on_show_asr(cq):
    uid = cq.from_user.id
    L_ui = ui_lang.get(uid, "ru")
    tr = _asr_store.get(uid, "")
    if not tr:
        await cq.answer("Расшифровка пока недоступна.", show_alert=False)
        return
    await cq.message.answer(f"Расшифровка (по запросу):\n{tr}", reply_markup=main_kb(L_ui))
    await cq.answer()

# ------------- ФОТО: структурный ответ + graceful fallback -------------
@dp.message(F.photo)
async def on_photo(m: Message):
    ensure_profiles(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    Lc   = content_lang.get(m.from_user.id, L_ui)
    # Скачаем фото (на будущее для OCR), но ответ сформируем сразу
    try:
        biggest = m.photo[-1]
        dest = Path(tempfile.gettempdir()) / f"{uuid.uuid4()}.jpg"
        await bot.download(file=biggest.file_id, destination=dest)
    except Exception:
        dest = None

    text = (
        "Карточка по фото:\n"
        "• Расшифровка (OCR): недоступна в этой версии — подключим позже.\n"
        "• Смысл/подписи: краткий комментарий и хэштеги по запросу.\n"
        "• Дизайн‑советы: контраст, безопасные зоны, 1–2 стикера."
    )
    await m.answer(text, reply_markup=main_kb(L_ui))
    # Кнопка «Показать расшифровку» оставляем — когда OCR появится, будет активно

# ------------- ВИДЕО: структурный ответ + graceful fallback -------------
@dp.message(F.video | F.video_note | (F.document & F.document.mime_type.startswith("video/")))
async def on_video(m: Message):
    ensure_profiles(m.from_user.id)
    L_ui = ui_lang[m.from_user.id]
    Lc   = content_lang.get(m.from_user.id, L_ui)
    msg = (
        "Карточка по видео:\n"
        "• Транскрипт с таймкодами: недоступен в этой версии — добавим.\n"
        "• Тезисы и инсайты: выдам кратко по запросу.\n"
        "• Обложка/заголовки A/B и план Shorts — готовы по теме."
    )
    await m.answer(msg, reply_markup=main_kb(L_ui))
    # При необходимости тут же озвучим краткое резюме
    try:
        kind, path, _ = tts_make(compose_reply(Lc, "short"), Lc)
        if kind == "voice":
            await m.answer_voice(voice=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
        else:
            await m.answer_audio(audio=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
    except Exception:
        pass

# ------------- FastAPI: healthcheck + webhook -------------
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
    if BASE:
        try:
            await bot.set_webhook(f"{BASE}/telegram/{SECRET}")
        except Exception as e:
            print("set_webhook error:", e)

# Локальный запуск (не обязателен на Railway)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
