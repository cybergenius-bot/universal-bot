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
import asyncio, os, re, tempfile, time, subprocess

# -------- Конфигурация --------
TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
SECRET = os.getenv("WEBHOOK_SECRET", "railway123")  # должен совпасть с URL
BASE   = os.getenv("BASE_URL", "")                  # напр.: https://universal-bot-production.up.railway.app
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

bot = Bot(TOKEN)
dp  = Dispatcher()
app = FastAPI()

# -------- Память пользователя (в проде — БД/Redis) --------
ui_lang: dict[int,str] = {}
last_content_langs: dict[int,list[str]] = {}
content_lang: dict[int,str] = {}

# -------- Локализация интерфейса (фиксируется пользователем) --------
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
            demo_text="Краткое резюме: понял запрос. Детали: отвечаю по сути. Чек‑лист: всё ок.",
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
            demo_text="Summary: got it. Details: responding to your point. Checklist: all good.",
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
            demo_text="תקציר: קיבלתי. פרטים: מגיב עניינית. צ׳ק‑ליסט: אפשר להמשיך.",
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

# -------- Детект языка контента (с «гистерезисом») --------
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
    counts: dict[str,int] = {}
    for c in arr:
        counts[c] = counts.get(c, 0) + 1
    best, mx = None, 0
    for k, v in counts.items():
        if v > mx:
            best, mx = k, v
    if mx >= 2:
        content_lang[user_id] = best
    return content_lang.get(user_id, candidate)

# -------- TTS: OGG/Opus, при отсутствии ffmpeg — MP3 --------
def tts_make(text: str, lang: str):
    tmp = tempfile.gettempdir()
    mp3 = os.path.join(tmp, f"{int(time.time()*1000)}.mp3")
    ogg = os.path.join(tmp, f"{int(time.time()*1000)+1}.ogg")

    tries = ["en","ru"]
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
            try:
                subprocess.run(
                    ["ffmpeg","-y","-i",mp3,"-c:a","libopus","-b:a","48k","-ac","1","-ar","48000",ogg],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return ("voice", ogg, mp3)   # ok: OGG/Opus
            except Exception:
                return ("audio", mp3, mp3)   # fallback: MP3
        except Exception as e:
            last_err = e
            continue
    raise last_err or RuntimeError("TTS failed")

# -------- Хендлеры --------
@dp.message(Command("start"))
async def on_start(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"
    L = ui_lang[uid]
    await m.answer(t_ui(L)["ready"], reply_markup=main_kb(L))

@dp.message(F.text)
async def on_text(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"
    L_ui = ui_lang[uid]
    t = t_ui(L_ui)
    txt = (m.text or "").strip()

    # Кнопка «Сменить язык»
    if txt in (t_ui("ru")["lang"], t_ui("en")["lang"], t_ui("he")["lang"]):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Русский", callback_data="ui_ru"),
             InlineKeyboardButton(text="English", callback_data="ui_en")],
            [InlineKeyboardButton(text="עברית", callback_data="ui_he")]
        ])
        await m.answer(t["lang_choose"], reply_markup=kb)
        return

    # «Дай голосом»
    if txt in (t_ui("ru")["say"], t_ui("en")["say"], t_ui("he")["say"]):
        Lc = content_lang.get(uid, "ru")
        demo = {
            "ru": "Озвучка: Сохраняйте спокойствие и продолжайте. Это демо‑голос.",
            "en": "Voice: Keep calm and carry on. This is a demo voice.",
            "he": "קול: שמרו על קור רוח והמשיכו. זה קול הדגמה.",
            "ja": "音声: 落ち着いて、前に進みましょう。これはデモ音声です。",
            "ar": "صوت: تحلَّ بالهدوء وواصل. هذا صوت تجريبي."
        }
        kind, path, mp3 = tts_make(demo.get(Lc, demo["ru"]), Lc)
        if kind == "voice":
            await m.answer_voice(voice=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
        else:
            await m.answer_audio(audio=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
        return

    # Обычный текст → автоязык контента (стабильный)
    candidate = detect_script_lang(txt) or "en"
    if candidate == "en" and len(txt) < 12:
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

@dp.callback_query(F.data.in_({"ui_ru","ui_en","ui_he"}))
async def on_ui_change(cq):
    mapping = {"ui_ru":"ru", "ui_en":"en", "ui_he":"he"}
    newL = mapping.get(cq.data, "ru")
    ui_lang[cq.from_user.id] = newL
    await cq.answer(t_ui(newL)["lang_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(newL)["lang_saved"])
    await bot.send_message(cq.message.chat.id, t_ui(newL)["ready"], reply_markup=main_kb(newL))

@dp.message(F.voice)
async def on_voice(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"
    L_ui = ui_lang[uid]
    Lc = content_lang.get(uid, L_ui)

    text = {
        "ru": "Краткое резюме: запрос принят. Детали: отвечаю по сути без повтора. Чек‑лист: уточним цель и следующий шаг.",
        "en": "Summary: received. Details: answering to the point, no echo. Checklist: clarify goal and next step.",
        "he": "תקציר: התקבל. פרטים: תשובה עניינית ללא חזרה. צ׳ק‑ליסט: נחדד מטרה וצעד הבא."
    }.get(Lc, "Summary: received. I will answer to the point.")

    await m.answer(text)
    try:
        kind, path, mp3 = tts_make(text, Lc)
        if kind == "voice":
            await m.answer_voice(voice=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
        else:
            await m.answer_audio(audio=FSInputFile(path), caption=t_ui(L_ui)["tts_caption"])
    except Exception:
        pass

# -------- FastAPI: healthcheck и вебхук --------
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

# -------- Локальный запуск (необязательно) --------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
