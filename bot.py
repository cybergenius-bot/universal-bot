---------- Логирование ----------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper() logging.basicConfig( level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s", handlers=[logging.StreamHandler(sys.stdout)], ) logger = logging.getLogger("bot") logging.getLogger("httpx").setLevel(logging.WARNING) logging.getLogger("openai").setLevel(logging.WARNING) logging.getLogger("telegram.vendor.ptb_urllib3").setLevel(logging.WARNING) logging.getLogger("apscheduler").setLevel(logging.WARNING) logging.getLogger("uvicorn.error").setLevel(logging.INFO) logging.getLogger("uvicorn.access").setLevel(logging.INFO)

---------- Переменные окружения ----------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "") TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "") PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/") WEBHOOK_PATH = "/telegram" WEBHOOK_URL = f"{PUBLIC_BASE_URL}{WEBHOOK_PATH}" if PUBLIC_BASE_URL else ""

---------- OpenAI (Whisper) ----------
try: from openai import OpenAI OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "") openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None except Exception as e: logger.warning("OpenAI SDK init warn: %s", e) openai_client = None

---------- Глобально: PTB Application ----------
application: Optional[Application] = None

---------- Утилиты скачивания и конвертации аудио ----------
class NamedBytesIO(io.BytesIO): def init(self, data: bytes, name: str): super().init(data) self.name = name

async def tg_download_bytes(bot, file_id: str) -> bytes: tg_file = await bot.get_file(file_id) bio = io.BytesIO() await tg_file.download_to_memory(out=bio) return bio.getvalue()

def ffmpeg_to_wav_sync(src: bytes) -> bytes: """ Конвертация входного аудио/видео в WAV 16kHz mono через ffmpeg. Синхронно (CPU). Вызывайте через asyncio.to_thread(). """ proc = subprocess.run( [ "ffmpeg", "-loglevel", "error", "-y", "-i", "pipe:0", "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1", ], input=src, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, ) return proc.stdout

def whisper_sync(data: bytes, name: str, lang: Optional[str] = "ru") -> str: """ Синхронный вызов OpenAI Whisper (audio.transcriptions.create). Возвращает только текст (response_format='text'). """ if not openai_client: raise RuntimeError("OPENAI_API_KEY не задан или OpenAI клиент не инициализирован.") resp = openai_client.audio.transcriptions.create( model="whisper-1", file=NamedBytesIO(data, name), response_format="text", language=lang or "ru", temperature=0, ) return resp # SDK возвращает str при response_format="text"

---------- Команды ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text( "Привет! 👋 Я универсальный ИИ‑бот.\n" "Бесплатно: 5 запросов. Тарифы: /pricing. Покупка: /buy\n" "Реферальная ссылка: /ref\n" "Пришлите текст/голос/фото/видео." )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Справка: пришлите текст/голос/фото/видео — отвечу. Команды: /pricing /buy /ref /status")

async def cmd_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Тарифы: Free 5 Q, $10 → 20 Q, $30 → 200 Q, $50 → безлимит/мес.")

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Покупка скоро. В работе PayPal и Telegram Stars.")

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE): me = await context.bot.get_me() user = update.effective_user ref_param = f"ref{user.id}" if user else "ref0" await update.message.reply_text(f"Ваша реф. ссылка: https://t.me/{me.username}?start={ref_param}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text("Статус: онлайн ✅")

---------- Текст ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE): if not update.message or not update.message.text: return await update.message.reply_text(f"Вы написали: {update.message.text.strip()}")

---------- Голос ----------
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE): if not update.message or not update.message.voice: return try: ogg = await tg_download_bytes(context.bot, update.message.voice.file_id) try: text = await asyncio.to_thread(whisper_sync, ogg, "audio.ogg", "ru") except Exception as e: logger.warning("OGG→Whisper failed, try ffmpeg→WAV: %s", e) wav = await asyncio.to_thread(ffmpeg_to_wav_sync, ogg) text = await asyncio.to_thread(whisper_sync, wav, "audio.wav", "ru") text = (text or "").strip() if not text: await update.message.reply_text("Не удалось распознать голос.") return await update.message.reply_text(text) except Exception as e: logger.exception("Voice STT error: %s", e) await update.message.reply_text("Не удалось распознать голос. Попробуйте ещё раз.")

---------- Аудио ----------
async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE): if not update.message or not update.message.audio: return try: b = await tg_download_bytes(context.bot, update.message.audio.file_id) try: name = (update.message.audio.file_name or "audio").lower() txt = await asyncio.to_thread(whisper_sync, b, name, "ru") except Exception: wav = await asyncio.to_thread(ffmpeg_to_wav_sync, b) txt = await asyncio.to_thread(whisper_sync, wav, "audio.wav", "ru") txt = (txt or "").strip() if not txt: await update.message.reply_text("Не удалось распознать аудио.") return await update.message.reply_text(txt) except Exception as e: logger.exception("Audio STT error: %s", e) await update.message.reply_text("Не удалось распознать аудио.")

---------- Видеокружок ----------
async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE): if not update.message or not update.message.video_note: return try: mp4 = await tg_download_bytes(context.bot, update.message.video_note.file_id)

    def mp4_to_wav(src: bytes) -> bytes:
        p = subprocess.run(
            [
                "ffmpeg", "-loglevel", "error", "-y",
                "-i", "pipe:0",
                "-vn",
                "-ac", "1",
                "-ar", "16000",
                "-f", "wav",
                "pipe:1",
            ],
            input=src,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return p.stdout

    wav = await asyncio.to_thread(mp4_to_wav, mp4)
    txt = await asyncio.to_thread(whisper_sync, wav, "audio.wav", "ru")
    txt = (txt or "").strip()
    if not txt:
        await update.message.reply_text("Не удалось распознать кружок.")
        return
    await update.message.reply_text(txt)
except Exception as e:
    logger.exception("VideoNote STT error: %s", e)
    await update.message.reply_text("Не удалось распознать кружок.")
---------- Регистрация хендлеров ----------
def register_handlers(app_ptb: Application): app_ptb.add_handler(CommandHandler("start", cmd_start)) app_ptb.add_handler(CommandHandler("help", cmd_help)) app_ptb.add_handler(CommandHandler("pricing", cmd_pricing)) app_ptb.add_handler(CommandHandler("buy", cmd_buy)) app_ptb.add_handler(CommandHandler("ref", cmd_ref)) app_ptb.add_handler(CommandHandler("status", cmd_status)) app_ptb.add_handler(MessageHandler(filters.VOICE, handle_voice), group=0) app_ptb.add_handler(MessageHandler(filters.AUDIO, handle_audio), group=0) app_ptb.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note), group=0) app_ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text), group=1)

---------- Создание PTB Application ----------
def create_ptb_application() -> Application: if not TELEGRAM_BOT_TOKEN: raise RuntimeError("TELEGRAM_BOT_TOKEN не установлен") app_ptb = Application.builder().token(TELEGRAM_BOT_TOKEN).concurrent_updates(True).build() register_handlers(app_ptb) return app_ptb

---------- FastAPI lifespan ----------
@asynccontextmanager async def lifespan(app: FastAPI): global application try: logger.info("Starting FastAPI lifespan init...") application = create_ptb_application() await application.initialize() await application.start()

    if WEBHOOK_URL and TELEGRAM_WEBHOOK_SECRET:
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:
            logger.warning("delete_webhook warn: %s", e)

        await application.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=TELEGRAM_WEBHOOK_SECRET,
            drop_pending_updates=True,
            allowed_updates=[
                "message", "edited_message", "callback_query", "chat_member",
                "pre_checkout_query", "channel_post", "edited_channel_post",
                "shipping_query",
            ],
        )
        logger.info("✅ Webhook установлен: %s", WEBHOOK_URL)
    else:
        logger.warning("PUBLIC_BASE_URL/TELEGRAM_WEBHOOK_SECRET не заданы — вебхук не установлен.")

    yield
except Exception as e:
    logger.error("Startup error: %s", e, exc_info=True)
    raise
finally:
    try:
        if application:
            try:
                await application.bot.delete_webhook(drop_pending_updates=False)
                logger.info("✅ Webhook удалён при остановке")
            except Exception as e:
                logger.warning("delete_webhook at shutdown warn: %s", e)
            await application.stop()
            await application.shutdown()
    except Exception as e:
        logger.error("Shutdown error: %s", e, exc_info=True)
---------- Приложение FastAPI ----------
app = FastAPI(title="Telegram Bot", version="1.0.0", lifespan=lifespan)

@app.get("/") async def root(): return {"message": "Telegram Bot работает!", "status": "OK"}

@app.get("/health/live") async def health_live(): return {"status": "ok"}

@app.get("/health/ready") async def health_ready(): try: if not application: return JSONResponse({"status": "starting"}, status_code=503) me = await application.bot.get_me() return {"status": "ready", "bot_username": me.username} except Exception as e: return JSONResponse({"status": "not_ready", "error": str(e)}, status_code=503)

@app.post("/telegram") async def telegram_webhook(request: Request): # Проверка секрета secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") if TELEGRAM_WEBHOOK_SECRET and secret != TELEGRAM_WEBHOOK_SECRET: logger.warning("Webhook 401: секрет не совпал") return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

try:
    data = await request.json()
    if not application:
        logger.error("PTB Application ещё не инициализирован")
        return JSONResponse({"ok": False, "error": "app not ready"}, status_code=503)

    update = Update.de_json(data, application.bot)
    if update:
        await application.process_update(update)
        return {"ok": True}
    logger.warning("Получен некорректный update")
    return JSONResponse({"ok": False, "error": "invalid update"}, status_code=400)
except Exception as e:
    logger.error("Webhook handle error: %s", e, exc_info=True)
    # Возвращаем 200, чтобы Telegram не долбил ретраями
    return JSONResponse({"ok": True})
if name == "main": import uvicorn uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)
