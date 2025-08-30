import os
import json
import asyncio
import logging
import tempfile
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from openai import OpenAI
logging.basicConfig(
level=logging.INFO,
format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("bot")
app = FastAPI(title="universal-telegram-bot")
class State:
def __init__(self) -> None:
    self.ready: bool = False
    self.mode: str = os.getenv("MODE", "webhook")
    self.application: Optional[Application] = None
    self.webhook_url: Optional[str] = None
    self.public_base_url: Optional[str] = os.getenv("PUBLIC_BASE_URL")
    self.webhook_secret: Optional[str] = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    self.telegram_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    self.openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    self.model_text: str = os.getenv("OPENAI_MODEL_TEXT", "gpt-4o-mini")
    self.model_whisper: str = os.getenv("OPENAI_MODEL_WHISPER", "whisper-1")
state = State()
@app.get("/health/live")
async def health_live():
return JSONResponse({"status": "ok"})
@app.get("/health/ready")
async def health_ready():
if state.ready and state.application is not None:
    return JSONResponse({"status": "ready"})
else:
    return JSONResponse({"status": "starting"})
@app.post("/telegram")
async def telegram_webhook(
request: Request,
x_telegram_bot_api_secret_token: Optional[str] = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
if state.mode != "webhook":
    raise HTTPException(status_code=503, detail="Webhook is not enabled")
if state.application is None or state.application.bot is None:
    raise HTTPException(status_code=503, detail="Application not initialized")
expected = state.webhook_secret
if expected:
    if x_telegram_bot_api_secret_token != expected:
        logger.warning("Webhook: secret token mismatch")
        raise HTTPException(status_code=403, detail="Forbidden")
else:
    logger.warning("Webhook: TELEGRAM_WEBHOOK_SECRET is not set — secret check disabled")
try:
    data = await request.json()
except Exception:
    data = json.loads((await request.body()).decode("utf-8") or "{}")
try:
    update = Update.de_json(data, state.application.bot)
except Exception as e:
    logger.exception("Update parse error: %s", e)
    raise HTTPException(status_code=400, detail="Bad update payload")
asyncio.create_task(state.application.process_update(update))
return JSONResponse({"ok": True})
@app.on_event("startup")
async def on_startup():
asyncio.create_task(_background_init())
async def _background_init():
try:
    await initialize_bot()
    state.ready = True
    logger.info("Initialization complete, ready")
except Exception as e:
    state.ready = False
    logger.exception("Initialization failed: %s", e)
async def initialize_bot():
if not state.telegram_token:
    logger.warning("TELEGRAM_BOT_TOKEN is not set — bot will not be initialized")
    return
application = Application.builder().token(state.telegram_token).build()
application.add_handler(CommandHandler("start", on_cmd_start))
application.add_handler(CommandHandler("help", on_cmd_help))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
application.add_handler(MessageHandler(filters.VOICE, on_voice))
application.add_handler(MessageHandler(filters.AUDIO, on_audio))
application.add_handler(MessageHandler(filters.PHOTO, on_photo))
application.add_handler(MessageHandler(filters.VIDEO, on_video))
await application.initialize()
if state.mode == "webhook":
    if not state.public_base_url:
        logger.warning("PUBLIC_BASE_URL is not set — cannot configure webhook")
    else:
        webhook_url = state.public_base_url.rstrip("/") + "/telegram"
        state.webhook_url = webhook_url
        await application.bot.set_webhook(url=webhook_url, secret_token=state.webhook_secret)
        logger.info("Webhook set: %s", webhook_url)
await application.start()
state.application = application
def get_openai_client() -> Optional[OpenAI]:
if not state.openai_api_key:
    logger.warning("OPENAI_API_KEY is not set — AI features disabled")
    return None
return OpenAI(api_key=state.openai_api_key)
async def on_cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.effective_message.reply_text(
    "Hi! I am a universal bot: text, voice/audio (Whisper), photo/video (basic), and long-form answers/Stories."
)
async def on_cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.effective_message.reply_text(
    "Available:\n"
    "- Text: analysis, summaries, Stories.\n"
    "- Voice/Audio: Whisper transcription.\n"
    "- Photo/Video: basic analysis.\n"
    "Running in webhook mode; use polling only for local debugging."
)
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
text = update.effective_message.text or ""
client = get_openai_client()
if not client:
    await update.effective_message.reply_text("Received text, but AI is unavailable (no OPENAI_API_KEY).")
    return
try:
    completion = client.chat.completions.create(
        model=state.model_text,
        messages=[
            {"role": "system", "content": "You are a concise and structured assistant."},
            {"role": "user", "content": f"Create a short, structured explanation/Story on:\n{text}"},
        ],
        temperature=0.4,
    )
    reply = completion.choices[0].message.content or "Done."
except Exception as e:
    logger.exception("Generation error: %s", e)
    reply = "Failed to generate an answer."
for chunk in split_long_message(reply):
    await update.effective_message.reply_text(chunk)
async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.effective_message or not update.effective_message.voice:
    return
client = get_openai_client()
if not client:
    await update.effective_message.reply_text("AI for transcription is unavailable (no OPENAI_API_KEY).")
    return
voice = update.effective_message.voice
file = await voice.get_file()
with tempfile.TemporaryDirectory() as td:
    ogg_path = os.path.join(td, "audio.ogg")
    wav_path = os.path.join(td, "audio.wav")
    await file.download_to_drive(ogg_path)
    await ffmpeg_to_wav(ogg_path, wav_path)
    text = await whisper_transcribe(client, wav_path)
    await update.effective_message.reply_text(f"Transcribed text:\n{text}")
async def on_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.effective_message or not update.effective_message.audio:
    return
client = get_openai_client()
if not client:
    await update.effective_message.reply_text("AI for transcription is unavailable (no OPENAI_API_KEY).")
    return
audio = update.effective_message.audio
file = await audio.get_file()
with tempfile.TemporaryDirectory() as td:
    in_path = os.path.join(td, "audio_input")
    wav_path = os.path.join(td, "audio.wav")
    await file.download_to_drive(in_path)
    await ffmpeg_to_wav(in_path, wav_path)
    text = await whisper_transcribe(client, wav_path)
    await update.effective_message.reply_text(f"Transcribed text:\n{text}")
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not update.effective_message or not update.effective_message.photo:
    return
client = get_openai_client()
if not client:
    await update.effective_message.reply_text("AI for image analysis is unavailable (no OPENAI_API_KEY).")
    return
await update.effective_message.reply_text("Photo received. Basic image analysis is enabled.")
async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.effective_message.reply_text("Video received. Keyframe extraction and analysis are in basic mode.")
def split_long_message(text: str, limit: int = 3500):
out = []
buf = []
size = 0
for line in text.splitlines(True):
    if size + len(line) > limit and buf:
        out.append("".join(buf))
        buf = [line]
        size = len(line)
    else:
        buf.append(line)
        size += len(line)
if buf:
    out.append("".join(buf))
return out or [text]
async def ffmpeg_to_wav(src_path: str, dst_path: str):
cmd = [
    "ffmpeg", "-y",
    "-i", src_path,
    "-ar", "16000",
    "-ac", "1",
    "-f", "wav",
    dst_path
]
logger.info("FFmpeg: %s", " ".join(cmd))
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.DEVNULL,
    stderr=asyncio.subprocess.DEVNULL,
)
rc = await proc.wait()
if rc != 0:
    raise RuntimeError(f"ffmpeg exited with code {rc}")
async def whisper_transcribe(client: OpenAI, wav_path: str) -> str:
try:
    with open(wav_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model=state.model_whisper,
            file=f
        )
    text = getattr(result, "text", None) or str(result)
    return text
except Exception as e:
    logger.exception("Whisper error: %s", e)
    return "Failed to transcribe audio."
