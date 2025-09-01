Copyfrom fastapi import FastAPI, Request, Response
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    Message, Update,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile
)
from gtts import gTTS
import os, re, tempfile, time, subprocess

# ------------------- Конфигурация -------------------
TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
SECRET = os.getenv("WEBHOOK_SECRET", "railway123")   # должен совпадать с частью пути вебхука
BASE   = os.getenv("BASE_URL", "")                   # напр.: https://universal-bot-production.up.railway.app
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

bot = Bot(TOKEN)
dp  = Dispatcher()
app = FastAPI()

# ------------------- Память пользователя (in‑mem) -------------------
ui_lang: dict[int, str] = {}              # язык интерфейса (ru|en|he) — фиксируется кнопкой
last_content_langs: dict[int, list[str]] = {}  # последние 3 детекции языка контента
content_lang: dict[int, str] = {}         # стабильный язык контента
_asr_store: dict[int, str] = {}           # последняя расшифровка войса (по кнопке показать)

# ------------------- Локализация интерфейса -------------------
def t_ui(lang: str = "ru"):
    data = {
        "ru": dict(
            ready="Готов. Выберите действие:",
            say="Дай голосом",
            show_tr="Показать расшифровку",
            lang="Сменить язык",
            mode="Режим ответа",
            lang_choose="Выберите язык интерфейса:",
            lang_saved="Язык интерфейса сохранён.",
            tts_caption="Озвучено",
        ),
        "en": dict(
            ready="Ready. Choose an action:",
            say="Speak it",
            show_tr="Show transcript",
            lang="Change language",
            mode="Reply mode",
            lang_choose="Choose interface language:",
            lang_saved="Interface language saved.",
            tts_caption="Voiced",
        ),
        "he": dict(
            ready="מוכן. בחרו פעולה:",
            say="השמע בקול",
            show_tr="הצג תמלול",
            lang="החלפת שפה",
            mode="מצב תגובה",
            lang_choose="בחרו שפת ממשק:",
            lang_saved="שפת הממשק נשמרה.",
            tts_caption="הוקרא",
        ),
    }
    return data.get(lang, data["ru"])

def main_kb(lang: str = "ru"):
    t = t_ui(lang)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t["say"]), KeyboardButton(text=t["show_tr"])],
            [KeyboardButton(text=t["lang"]), KeyboardButton(text=t["mode"])],
        ],
        resize_keyboard=True
    )

# ------------------- Детект языка контента (без «скачков») -------------------
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

# ------------------- TTS (OGG/Opus, fallback MP3) -------------------
def tts_make(text: str, lang: str):
    tmp = tempfile.gettempdir()
    mp3 = os.path.join(tmp, f"{int(time.time()*1000)}.mp3")
    ogg = os.path.join(tmp, f"{int(time.time()*1000)+1}.ogg")

    tries = ["en", "ru"]
    if lang == "he":
        tries = ["he", "iw"] + tries
    elif lang == "zh":
        tries = ["zh-CN", "zh-TW"] + tries
    else:
        tries = [lang] + tries

    last_err = None
    for L in tries:
        try:
            gTTS(text=text, lang=L).save(mp3)
            # Конвертация в OGG/Opus
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", mp3, "-c:a", "libopus", "-b:a", "48k", "-ac", "1", "-ar", "48000", ogg],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return ("voice", ogg, mp3)
            except Exception:
                return ("audio", mp3, mp3)  # если ffmpeg недоступен — отправим MP3 как audio
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("TTS failed")

# ------------------- Хендлеры -------------------
@dp.message(Command("start"))
async def on_start(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"  # интерфейс по умолчанию — RU (фиксируется кнопкой)
    L = ui_lang[uid]
    await m.answer(t_ui(L)["ready"], reply_markup=main_kb(L))

@dp.message(F.text)
async def on_text(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"
    L_ui = ui_lang[uid]
    t = t_ui(L_ui)
    txt = (m.text or "").trim()

    # 1) Кнопка «Сменить язык»
    if txt in (t_ui("ru")["lang"], t_ui("en")["lang"], t_ui("he")["lang"]):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Русский", callback_data="ui_ru"),
             InlineKeyboardButton(text="English", callback_data="ui_en")],
            [InlineKeyboardButton(text="עברית", callback_data="ui_he")]
        ])
        await m.answer(t["lang_choose"], reply_markup=kb)
        return

    # 2) Кнопка/фраза «Дай голосом»
    if txt in (t_ui("ru")["say"], t_ui("en")["say"], t_ui("he")["say"]):
        Lc = content_lang.get(uid, "ru")
        demo = {
            "ru": "Озвучка: Сохраняйте спокойствие и продолжайте. Это демо‑голос.",
            "en": "Voice: Keep calm and carry on. This is a demo voice.",
            "he": "קול: שמרו על קור רוח והמשיכו. זה קול הדגמה.",
            "ja": "音声: 落ち着いて、前に進みましょう。これはデモ音声です。",
            "ar": "صوت: تحلَّ بالهدوء وواصل. هذا صوت تجريبي.",
        }
        kind, path, _ = tts_make(demo.get(Lc, demo["ru"]), Lc)
        if kind == "voice":
            await m.answer_voice(voice=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
        else:
            await m.answer_audio(audio=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
        return

    # 3) Обычный текст → автоязык контента (стабильный)
    candidate = detect_script_lang(txt) or "en"
    if candidate == "en" and len(txt) < 12:  # защита от "ok/hi"
        candidate = content_lang.get(uid, "ru")
    stable = update_content_lang(uid, candidate)

    replies = {
        "ru": "Краткое резюме: понял запрос. Детали: отвечаю по‑русски. Чек‑лист: всё ок.",
        "en": "Summary: got your request. Details: replying in English. Checklist: all good.",
        "he": "תקציר: קיבלתי. פרטים: עונה בעברית. צ׳ק‑ליסט: הכל בסדר.",
        "ja": "要約: 了解しました。詳細: 日本語で回答します。チェック: OKです。",
        "ar": "ملخص: تم الاستلام. التفاصيل: سأرد بالعربية. قائمة التحقق: تمام.",
    }
    await m.answer(replies.get(stable, replies["ru"]), reply_markup=main_kb(L_ui))

# -------- Анти‑эхо для голосовых: без повтора речи; расшифровка только по кнопке --------
async def _summarize_without_echo(asr_text: str, lang: str) -> str:
    if lang == "he":
        return (
            "תקציר: קיבלתי את בקשת הקול.\n"
            "פרטים: אענה עניינית בלי לחזור על המילים שלך.\n"
            "צ׳ק־ליסט: האם תרצה פירוט או צעד הבא?"
        )
    if lang == "en":
        return (
            "Summary: your voice request is received.\n"
            "Details: I’ll answer to the point without echoing your words.\n"
            "Checklist: want details or next step?"
        )
    return (
        "Краткое резюме: запрос принят.\n"
        "Детали: отвечаю по сути, без повтора ваших слов.\n"
        "Чек‑лист: нужны детали или следующий шаг?"
    )

@dp.message(F.voice)
async def on_voice(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"
    L_ui = ui_lang[uid]
    Lc = content_lang.get(uid, L_ui)

    # 1) ВАША интеграция ASR (если есть) — здесь поставьте результат распознавания:
    asr_text = ""  # <- подставьте текст из вашего ASR; по умолчанию не показываем
    _asr_store[uid] = asr_text

    # 2) Структурный ответ без повтора речи
    text = await _summarize_without_echo(asr_text, Lc)
    await m.answer(text, reply_markup=main_kb(L_ui))

    # 3) Кнопка «Показать расшифровку» (по запросу)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t_ui(L_ui)["show_tr"], callback_data="show_asr")]
    ])
    await m.answer("Готов показать расшифровку по кнопке:", reply_markup=kb)

    # 4) Озвучка структурного ответа (TTS)
    try:
        kind, path, _ = tts_make(text, Lc)
        if kind == "voice":
            await m.answer_voice(voice=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
        else:
            await m.answer_audio(audio=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
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

# ------------------- FastAPI: healthcheck и вебхук -------------------
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
