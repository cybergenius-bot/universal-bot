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
import os, re, tempfile, time, subprocess

# ------------------- Конфигурация -------------------
TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN")
SECRET = os.getenv("WEBHOOK_SECRET", "railway123")   # должен совпасть с частью пути вебхука
BASE   = os.getenv("BASE_URL", "")                   # напр.: https://universal-bot-production.up.railway.app
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не задан")

bot = Bot(TOKEN)
dp  = Dispatcher()
app = FastAPI()

# ------------------- Память пользователя (in‑mem) -------------------
ui_lang: dict[int, str] = {}               # язык интерфейса (ru|en|he) — фиксируется кнопкой
last_content_langs: dict[int, list[str]] = {}  # последние 3 детекции языка контента
content_lang: dict[int, str] = {}          # стабильный язык контента
_asr_store: dict[int, str] = {}            # последняя расшифровка войса (по кнопке показать)
reply_mode: dict[int, str] = {}            # 'short' | 'expanded' | 'deep'  (по умолчанию 'expanded')

# ------------------- Локализация интерфейса -------------------
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

# ------------------- Генерация ответа по режиму -------------------
def compose_reply(lang: str, mode: str) -> str:
    # defaults
    if mode not in ("short", "expanded", "deep"):
        mode = "expanded"
    if lang == "he":
        base = {
            "short": "תקציר: קיבלתי. אענה בקצרה.",
            "expanded": "תקציר: קיבלתי. פרטים: אענה בצורה ברורה ומועילה.",
            "deep": "תקציר: קיבלתי. פרטים מעמיקים והקשר יינתנו לפי הצורך."
        }
    elif lang == "en":
        base = {
            "short": "Summary: received. I’ll answer briefly.",
            "expanded": "Summary: received. Details: I’ll provide a clear, useful answer.",
            "deep": "Summary: received. In‑depth: I’ll add context, steps and caveats."
        }
    else:
        base = {
            "short": "Кратко: запрос принят. Отвечаю по существу.",
            "expanded": "Развёрнуто: запрос принят. Дам понятный и полезный ответ.",
            "deep": "Глубоко: дам контекст, шаги, нюансы и оговорки."
        }
    return base[mode]

def tts_caption_for_mode(lang: str, mode: str) -> str:
    t = t_ui(lang)
    return f'{t["tts_caption"]} · {{"short":"Кратко","expanded":"Развёрнуто","deep":"Глубоко"}.get(mode,"Развёрнуто")}'

# ------------------- Хендлеры -------------------
@dp.message(Command("start"))
async def on_start(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"  # интерфейс по умолчанию — RU (фиксируется кнопкой)
    if uid not in reply_mode:
        reply_mode[uid] = "expanded"
    L = ui_lang[uid]
    await m.answer(t_ui(L)["ready"], reply_markup=main_kb(L))

@dp.message(F.text)
async def on_text(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"
    if uid not in reply_mode:
        reply_mode[uid] = "expanded"
    L_ui = ui_lang[uid]
    t = t_ui(L_ui)
    txt = (m.text or "").strip()

    # 1) Кнопка «Сменить язык»
    if txt in (t_ui("ru")["lang"], t_ui("en")["lang"], t_ui("he")["lang"]):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Русский", callback_data="ui_ru"),
             InlineKeyboardButton(text="English", callback_data="ui_en")],
            [InlineKeyboardButton(text="עברית", callback_data="ui_he")]
        ])
        await m.answer(t["lang_choose"], reply_markup=kb)
        return

    # 2) Кнопка «Режим ответа»
    if txt in (t_ui("ru")["mode"], t_ui("en")["mode"], t_ui("he")["mode"]):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=t["mode_short"], callback_data="rm_short"),
             InlineKeyboardButton(text=t["mode_expanded"], callback_data="rm_expanded"),
             InlineKeyboardButton(text=t["mode_deep"], callback_data="rm_deep")]
        ])
        await m.answer(t["mode_choose"], reply_markup=kb)
        return

    # 3) Текстовые триггеры: «Ответ: кратко/развёрнуто/глубоко»
    low = txt.lower()
    if low.startswith("ответ:"):
        if "крат" in low or "short" in low:
            reply_mode[uid] = "short"
        elif "глуб" in low or "deep" in low:
            reply_mode[uid] = "deep"
        else:
            reply_mode[uid] = "expanded"
        await m.answer(t["mode_saved"], reply_markup=main_kb(L_ui))
        return

    # 4) «Дай голосом»
    if txt in (t_ui("ru")["say"], t_ui("en")["say"], t_ui("he")["say"]):
        Lc = content_lang.get(uid, "ru")
        mode = reply_mode.get(uid, "expanded")
        voice_text = compose_reply(Lc, mode)
        kind, path, _ = tts_make(voice_text, Lc)
        if kind == "voice":
            await m.answer_voice(voice=FSInputFile(path), caption=tts_caption_for_mode(L_ui, mode))
        else:
            await m.answer_audio(audio=FSInputFile(path), caption=tts_caption_for_mode(L_ui, mode))
        return

    # 5) Обычный текст → автоязык контента (стабильный)
    candidate = detect_script_lang(txt) or "en"
    if candidate == "en" and len(txt) < 12:  # защита от "ok/hi"
        candidate = content_lang.get(uid, "ru")
    stable = update_content_lang(uid, candidate)

    mode = reply_mode.get(uid, "expanded")
    reply = compose_reply(stable, mode)
    await m.answer(reply, reply_markup=main_kb(L_ui))

# -------- Анти‑эхо для голосовых: без повтора речи; расшифровка только по кнопке --------
async def _summarize_without_echo(asr_text: str, lang: str, mode: str) -> str:
    if lang == "he":
        base = {
            "short": "תקציר: קיבלתי. בלי לחזור על המילים שלך.",
            "expanded": "תקציר: קיבלתי. אענה עניינית, ללא חזרה על הטקסט.",
            "deep": "תקציר: קיבלתי. אספק תשובה מעמיקה ללא הדהוד, עם צעדים הבאים."
        }
        return base[mode]
    if lang == "en":
        base = {
            "short": "Summary: received. No echoing your words.",
            "expanded": "Summary: received. Answering to the point, without echo.",
            "deep": "Summary: received. In‑depth answer without echo, with next steps."
        }
        return base[mode]
    base = {
        "short": "Кратко: запрос принят. Без повтора ваших слов.",
        "expanded": "Развёрнуто: отвечаю по сути, не повторяя ваш текст.",
        "deep": "Глубоко: структурный ответ без повтора + следующие шаги."
    }
    return base[mode]

@dp.message(F.voice)
async def on_voice(m: Message):
    uid = m.from_user.id
    if uid not in ui_lang:
        ui_lang[uid] = "ru"
    if uid not in reply_mode:
        reply_mode[uid] = "expanded"
    L_ui = ui_lang[uid]
    Lc = content_lang.get(uid, L_ui)
    mode = reply_mode.get(uid, "expanded")

    # 1) Интеграция ASR (если есть) — положите результат сюда:
    asr_text = ""  # <- подставьте текст из вашего ASR; по умолчанию не показываем
    _asr_store[uid] = asr_text

    # 2) Структурный ответ без повтора речи
    text = await _summarize_without_echo(asr_text, Lc, mode)
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

# ---- Смена языка интерфейса и режима ответа (callback) ----
@dp.callback_query(F.data.in_({"ui_ru","ui_en","ui_he"}))
async def on_ui_change(cq):
    mapping = {"ui_ru":"ru", "ui_en":"en", "ui_he":"he"}
    newL = mapping.get(cq.data, "ru")
    ui_lang[cq.from_user.id] = newL
    await cq.answer(t_ui(newL)["lang_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(newL)["lang_saved"])
    await bot.send_message(cq.message.chat.id, t_ui(newL)["ready"], reply_markup=main_kb(newL))

@dp.callback_query(F.data.in_({"rm_short","rm_expanded","rm_deep"}))
async def on_mode_change(cq):
    uid = cq.from_user.id
    L_ui = ui_lang.get(uid, "ru")
    if cq.data == "rm_short":
        reply_mode[uid] = "short"
    elif cq.data == "rm_deep":
        reply_mode[uid] = "deep"
    else:
        reply_mode[uid] = "expanded"
    await cq.answer(t_ui(L_ui)["mode_saved"], show_alert=False)
    await cq.message.edit_text(t_ui(L_ui)["mode_saved"])
    await bot.send_message(cq.message.chat.id, t_ui(L_ui)["ready"], reply_markup=main_kb(L_ui))

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
