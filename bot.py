import os
import io
import asyncio
import logging
import subprocess
import base64
from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("bot")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
WEBHOOK_PATH = "/telegram"
WEBHOOK_URL = f"{PUBLIC_BASE_URL}{WEBHOOK_PATH}" if PUBLIC_BASE_URL else ""
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-4o-mini")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
OPENAI_WHISPER_MODEL = os.getenv("OPENAI_WHISPER_MODEL", "whisper-1")
try:
from openai import OpenAI
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception as e:
logger.warning("OpenAI SDK init warn: %s", e)
openai_client = None
application: Optional[Application] = None
class NamedBytesIO(io.BytesIO):
def __init__(self, data: bytes, name: str):
    super().__init__(data); self.name = name
def chunk_text(text: str, limit: int = 3500) -> List[str]:
chunks: List[str] = []; current = []; size = 0
for line in text.splitlines(keepends=True):
    if size + len(line) > limit and current:
        chunks.append("".join(current)); current, size = [], 0
    current.append(line); size += len(line)
if current: chunks.append("".join(current))
return chunks or [text]
async def send_long_text(update: Update, text: str):
for part in chunk_text(text, 3500):
    await update.message.reply_text(part, disable_web_page_preview=True)
async def tg_download_bytes(bot, file_id: str) -> bytes:
tg_file = await bot.get_file(file_id); bio = io.BytesIO()
await tg_file.download_to_memory(out=bio); return bio.getvalue()
def ffmpeg_to_wav_sync(src: bytes) -> bytes:
p = subprocess.run(["ffmpeg","-loglevel","error","-y","-i","pipe:0","-vn","-ac","1","-ar","16000","-f","wav","pipe:1"],
                   input=src, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
return p.stdout
def extract_keyframes_sync(src: bytes, frames: int = 3, scale_width: int = 640) -> List[bytes]:
p = subprocess.run(["ffmpeg","-loglevel","error","-y","-i","pipe:0","-vf",f"fps=1,scale={scale_width}:-1",
                    "-vframes",str(frames),"-f","image2pipe","-vcodec","mjpeg","pipe:1"],
                   input=src, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
data = p.stdout; imgs = []; SOI = b"\xff\xd8"; EOI = b"\xff\xd9"; i = 0
while True:
    s = data.find(SOI, i); 
    if s == -1: break
    e = data.find(EOI, s); 
    if e == -1: break
    imgs.append(data[s:e+2]); i = e + 2
return imgs[:frames]
def whisper_sync(data: bytes, name: str, lang: Optional[str] = "ru") -> str:
if not openai_client: raise RuntimeError("OPENAI_API_KEY не задан или OpenAI клиент не инициализирован.")
text = openai_client.audio.transcriptions.create(model=OPENAI_WHISPER_MODEL,
                                                 file=NamedBytesIO(data, name),
                                                 response_format="text", language=lang or "ru",
                                                 temperature=0)
return text
def _data_url(image_bytes: bytes) -> str:
return "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
def llm_generate_sync(prompt: str, system: str = "Ты внимательный и развернутый ассистент.",
                  max_tokens: int = 1600, temperature: float = 0.7) -> str:
if not openai_client: raise RuntimeError("OPENAI_API_KEY не задан, текстовая генерация недоступна.")
resp = openai_client.chat.completions.create(model=OPENAI_TEXT_MODEL,
    messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
    max_tokens=max_tokens, temperature=temperature)
return (resp.choices[0].message.content or "").strip()
def vision_analyze_sync(image_bytes: bytes, question: str = "Опиши подробно, что на фото, и извлеки важный текст.") -> str:
if not openai_client: raise RuntimeError("OPENAI_API_KEY не задан, визуальный анализ недоступен.")
data_url = _data_url(image_bytes)
resp = openai_client.chat.completions.create(model=OPENAI_VISION_MODEL,
    messages=[{"role":"system","content":"Ты визуальный помощник. Кратко объекты, затем подробное описание и выводы. Если есть текст — процитируй (OCR)."},
              {"role":"user","content":[{"type":"text","text":question},{"type":"image_url","image_url":{"url":data_url}}]}],
    max_tokens=900, temperature=0.5)
return (resp.choices[0].message.content or "").strip()
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Привет! 👋 Я универсальный ИИ‑бот.\nУмею: текст (подробные ответы и Stories), голос/аудио (распознаю), фото/видео (анализирую).\nКоманды: /help /story /pricing /buy /ref /status")
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Справка:\n• Пишите вопрос — отвечу развёрнуто\n• Голос/аудио — распознаю текст\n• Фото — опишу и извлеку текст\n• Видео — извлеку аудио и кадры, сделаю краткое содержание\n• /story <тема> — напишу объёмный рассказ")
async def cmd_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Тарифы: Free 5 Q, $10 → 20 Q, $30 → 200 Q, $50 → безлимит/мес.")
async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Покупка скоро. В работе PayPal/Stripe/Telegram Stars.")
async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
me = await context.bot.get_me(); user = update.effective_user
ref_param = f"ref{user.id}" if user else "ref0"
await update.message.reply_text(f"Ваша реф. ссылка: https://t.me/{me.username}?start={ref_param}")
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("Статус: онлайн ✅")
async def cmd_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.message: return
topic = (update.message.text or "").split(" ", 1)
prompt = topic[1].strip() if len(topic) > 1 else "Свободная тема. Напиши вдохновляющий рассказ на 1200–1800 слов."
try:
    text = await asyncio.to_thread(llm_generate_sync,
        f"Напиши художественный рассказ с яркими сценами, диалогами, динамикой, сильной концовкой. Тема/ограничения: {prompt}",
        "Ты опытный писатель. Пиши образно, структурировано, с логикой и стильными переходами.",
        max_tokens=2000, temperature=0.85)
    await send_long_text(update, text or "Не удалось создать рассказ.")
except Exception as e:
    logger.exception("Story error: %s", e)
    await update.message.reply_text("Ошибка генерации рассказа.")
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.message or not update.message.text: return
user_text = update.message.text.strip(); lower = user_text.lower()
if lower.startswith(("story:", "история:", "рассказ:")):
    update.message.text = "/story " + user_text.split(":", 1)[1]; return await cmd_story(update, context)
try:
    text = await asyncio.to_thread(llm_generate_sync,
        f"Ответь максимально подробно и структурировано. Вопрос: {user_text}",
        "Ты эксперт‑ассистент. Даёшь обстоятельные, практичные ответы.",
        max_tokens=1400, temperature=0.65)
    await send_long_text(update, text or "Не удалось сгенерировать ответ.")
except Exception as e:
    logger.exception("Text LLM error: %s", e)
    await update.message.reply_text("Ошибка генерации ответа.")
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.message or not update.message.voice: return
try:
    ogg = await tg_download_bytes(context.bot, update.message.voice.file_id)
    try:
        text = await asyncio.to_thread(whisper_sync, ogg, "audio.ogg", "ru")
    except Exception as e:
        logger.warning("OGG→Whisper failed, try ffmpeg→WAV: %s", e)
        wav = await asyncio.to_thread(ffmpeg_to_wav_sync, ogg)
        text = await asyncio.to_thread(whisper_sync, wav, "audio.wav", "ru")
    text = (text or "").strip()
    if not text: return await update.message.reply_text("Не удалось распознать голос.")
    answer = await asyncio.to_thread(llm_generate_sync,
        f"Сформулируй развёрнутый ответ на распознанный запрос: {text}",
        "Ты эксперт‑ассистент. Даёшь обстоятельные ответы.", max_tokens=1000, temperature=0.6)
    await send_long_text(update, answer or text)
except Exception as e:
    logger.exception("Voice STT/LLM error: %s", e)
    await update.message.reply_text("Не удалось обработать голос. Попробуйте ещё раз.")
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.message or not update.message.audio: return
try:
    b = await tg_download_bytes(context.bot, update.message.audio.file_id)
    try:
        name = (update.message.audio.file_name or "audio").lower()
        txt = await asyncio.to_thread(whisper_sync, b, name, "ru")
    except Exception:
        wav = await asyncio.to_thread(ffmpeg_to_wav_sync, b)
        txt = await asyncio.to_thread(whisper_sync, wav, "audio.wav", "ru")
    txt = (txt or "").strip()
    if not txt: return await update.message.reply_text("Не удалось распознать аудио.")
    answer = await asyncio.to_thread(llm_generate_sync,
        f"Пользователь прислал аудио. Распознанный текст: {txt}. Дай развёрнутый ответ.",
        max_tokens=1000, temperature=0.6)
    await send_long_text(update, answer or txt)
except Exception as e:
    logger.exception("Audio STT/LLM error: %s", e)
    await update.message.reply_text("Не удалось обработать аудио.")
async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.message or not update.message.video_note: return
try:
    mp4 = await tg_download_bytes(context.bot, update.message.video_note.file_id)
    wav = await asyncio.to_thread(ffmpeg_to_wav_sync, mp4)
    txt = await asyncio.to_thread(whisper_sync, wav, "circle.wav", "ru")
    txt = (txt or "").strip()
    if not txt: return await update.message.reply_text("Не удалось распознать кружок.")
    summary = await asyncio.to_thread(llm_generate_sync, f"Суммаризируй и структурируй содержание: {txt}", max_tokens=800)
    await send_long_text(update, summary or txt)
except Exception as e:
    logger.exception("VideoNote STT/LLM error: %s", e)
    await update.message.reply_text("Не удалось обработать кружок.")
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.message or not update.message.photo: return
try:
    best = update.message.photo[-1]
    b = await tg_download_bytes(context.bot, best.file_id)
    analysis = await asyncio.to_thread(vision_analyze_sync, b, "Опиши предметы, контекст; извлеки текст (если есть); сделай выводы.")
    await send_long_text(update, analysis or "Не удалось проанализировать фото.")
except Exception as e:
    logger.exception("Photo vision error: %s", e)
    await update.message.reply_text("Не удалось обработать фото.")
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.message or not update.message.video: return
try:
    vid = await tg_download_bytes(context.bot, update.message.video.file_id)
    wav = await asyncio.to_thread(ffmpeg_to_wav_sync, vid)
    transcript = await asyncio.to_thread(whisper_sync, wav, "video.wav", "ru")
    transcript = (transcript or "").strip()
    summary = ""
    if transcript:
        summary = await asyncio.to_thread(llm_generate_sync, f"Кратко перескажи содержание видео (по транскрипту): {transcript}", max_tokens=900)
    frames = await asyncio.to_thread(extract_keyframes_sync, vid, 3, 640)
    vision_parts: List[str] = []
    for i, img in enumerate(frames, 1):
        try:
            part = await asyncio.to_thread(vision_analyze_sync, img, f"Кадр {i}. Кратко: что видно, важные детали/текст.")
            if part: vision_parts.append(f"Кадр {i}:\n{part}")
        except Exception as ex:
            logger.warning("Vision frame %s error: %s", i, ex)
    out = ""
    if summary: out += "Суммаризация по аудио:\n" + summary + "\n\n"
    if vision_parts: out += "Визуальный анализ кадров:\n" + "\n\n".join(vision_parts)
    await send_long_text(update, out or "Не удалось проанализировать видео.")
except Exception as e:
    logger.exception("Video analyze error: %s", e)
    await update.message.reply_text("Не удалось обработать видео.")
def register_handlers(app_ptb: Application):
app_ptb.add_handler(CommandHandler("start", cmd_start))
app_ptb.add_handler(CommandHandler("help", cmd_help))
app_ptb.add_handler(CommandHandler("pricing", cmd_pricing))
app_ptb.add_handler(CommandHandler("buy", cmd_buy))
app_ptb.add_handler(CommandHandler("ref", cmd_ref))
app_ptb.add_handler(CommandHandler("status", cmd_status))
app_ptb.add_handler(CommandHandler("story", cmd_story))
app_ptb.add_handler(MessageHandler(filters.VOICE, handle_voice), group=0)
app_ptb.add_handler(MessageHandler(filters.AUDIO, handle_audio), group=0)
app_ptb.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note), group=0)
app_ptb.add_handler(MessageHandler(filters.VIDEO, handle_video), group=0)
app_ptb.add_handler(MessageHandler(filters.PHOTO, handle_photo), group=0)
app_ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text), group=1)
def create_ptb_application() -> Application:
if not TELEGRAM_BOT_TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN не установлен")
app_ptb = Application.builder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build()
register_handlers(app_ptb); return app_ptb
@asynccontextmanager
async def lifespan(app: FastAPI):
global application
try:
    logger.info("Starting FastAPI lifespan init...")
    application = create_ptb_application()
    await application.initialize(); await application.start()
    if WEBHOOK_URL and TELEGRAM_WEBHOOK_SECRET:
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.warning("delete_webhook warn: %s", e)
        await application.bot.set_webhook(url=WEBHOOK_URL, secret_token=TELEGRAM_WEBHOOK_SECRET,
            drop_pending_updates=True,
            allowed_updates=["message","edited_message","callback_query","chat_member","pre_checkout_query","channel_post","edited_channel_post","shipping_query"])
        logger.info("Webhook установлен: %s", WEBHOOK_URL)
    else:
        logger.warning("PUBLIC_BASE_URL/TELEGRAM_WEBHOOK_SECRET не заданы — вебхук не установлен.")
    yield
except Exception as e:
    logger.error("Startup error: %s", e, exc_info=True); raise
finally:
    try:
        if application:
            try:
                await application.bot.delete_webhook(drop_pending_updates=False)
            except Exception as e:
                logger.warning("delete_webhook at shutdown warn: %s", e)
            await application.stop(); await application.shutdown()
    except Exception as e:
        logger.error("Shutdown error: %s", e, exc_info=True)
app = FastAPI(title="Telegram Bot", version="1.1.0", lifespan=lifespan)
@app.get("/")
async def root():
return {"message": "Telegram Bot работает!", "status": "OK"}
@app.get("/health/live")
async def health_live():
return {"status": "ok"}
@app.get("/health/ready")
async def health_ready():
try:
    if not application: return JSONResponse({"status": "starting"}, status_code=503)
    me = await application.bot.get_me()
    return {"status": "ready", "bot_username": me.username}
except Exception as e:
    return JSONResponse({"status": "not_ready", "error": str(e)}, status_code=503)
@app.post("/telegram")
async def telegram_webhook(request: Request):
secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
if TELEGRAM_WEBHOOK_SECRET and secret != TELEGRAM_WEBHOOK_SECRET:
    return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
try:
    data = await request.json()
    if not application:
        return JSONResponse({"ok": False, "error": "app not ready"}, status_code=503)
    update = Update.de_json(data, application.bot)
    if update:
        await application.process_update(update); return {"ok": True}
    return JSONResponse({"ok": False, "error": "invalid update"}, status_code=200)
except Exception:
    return JSONResponse({"ok": True})
if name == "main":
mode = os.getenv("MODE", "webhook").lower()
if mode == "polling":
    app_ptb = create_ptb_application()
    app_ptb.run_polling(allowed_updates=["message","edited_message","callback_query","chat_member","pre_checkout_query","channel_post","edited_channel_post","shipping_query"],
                        drop_pending_updates=True)
else:
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
