import os
import json
import time
import asyncio
import ipaddress
import logging
import secrets
import string
import tempfile
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from collections import defaultdict, deque

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

# --- Correlation-ID middleware: опционально, с graceful fallback ---
try:
    from asgi_correlation_id import CorrelationIdMiddleware, CorrelationIdFilter  # type: ignore
except Exception:
    class CorrelationIdMiddleware:  # no-op middleware
        def __init__(self, app, header_name: str = "X-Request-ID", *args, **kwargs):
            self.app = app
        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)
    class CorrelationIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "correlation_id"):
                record.correlation_id = "-"
            return True

# --- Настройки окружения ---
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or "").strip()
if not WEBHOOK_URL:
    base_url = (os.getenv("BASE_URL") or "").strip().rstrip("/")
    if base_url:
        WEBHOOK_URL = f"{base_url}/telegram"

TELEGRAM_WEBHOOK_SECRET_ENV = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*")
TELEGRAM_ALLOWED_UPDATES = os.getenv("TELEGRAM_ALLOWED_UPDATES", "message,callback_query")
TELEGRAM_DROP_PENDING_UPDATES = os.getenv("TELEGRAM_DROP_PENDING_UPDATES", "true").lower() == "true"
TELEGRAM_MAX_CONNECTIONS = int(os.getenv("TELEGRAM_MAX_CONNECTIONS", "40"))
ENABLE_IP_ALLOWLIST = os.getenv("ENABLE_IP_ALLOWLIST", "false").lower() == "true"
TELEGRAM_IP_RANGES = os.getenv("TELEGRAM_IP_RANGES", "")  # например: "149.154.160.0/20,91.108.4.0/22"
CORRELATION_ID_HEADER = os.getenv("CORRELATION_ID_HEADER", "X-Request-ID")
MAX_TELEGRAM_PAYLOAD_BYTES = int(os.getenv("MAX_TELEGRAM_PAYLOAD_BYTES", "1048576"))

# OpenAI настройки
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()  # основной диалог
OPENAI_TEMP = float(os.getenv("OPENAI_TEMPERATURE", "0.5"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "700"))
OPENAI_ENABLE_VOICE = os.getenv("OPENAI_ENABLE_VOICE", "true").lower() == "true"  # распознавать voice
AI_SYSTEM_PROMPT = os.getenv("AI_SYSTEM_PROMPT", "You are a helpful, concise, and safe assistant. Reply in the user's language.")

# --- Логирование + фильтр для correlation_id ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] [%(correlation_id)s] %(message)s",
)
for _h in logging.getLogger().handlers:
    _h.addFilter(CorrelationIdFilter())
logger = logging.getLogger("bot")

# --- Telegram: PTB Application и Handlers ---
from telegram import Update, Bot, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

application: Optional[Application] = None  # PTB Application
bot: Optional[Bot] = None  # Telegram Bot

# Текущий секрет вебхука (из env или сгенерированный на старте)
CURRENT_WEBHOOK_SECRET: Optional[str] = None

def _generate_secret(length: int = 48) -> str:
    # Разрешённые символы по требованиям Telegram (A-Z a-z 0-9 _ -)
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))

# --- OpenAI клиент (async) ---
openai_client = None
OPENAI_ENABLED = bool(OPENAI_API_KEY)

if OPENAI_ENABLED:
    try:
        from openai import AsyncOpenAI
    except Exception:
        OPENAI_ENABLED = False
        logger.warning("OpenAI client not installed; AI disabled")

# --- SQLAlchemy (опционально), fallback на in-memory если модуля нет ---
try:
    from sqlalchemy import String, Integer, BigInteger, Text, DateTime, func, select, text as sql_text
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    SQLA_AVAILABLE = True

    class Base(DeclarativeBase):
        pass

    class User(Base):
        __tablename__ = "users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        tg_user_id: Mapped[int] = mapped_column(BigInteger, index=True, unique=True)
        username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
        first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
        last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
        created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())
        updated_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    class MessageLog(Base):
        __tablename__ = "message_logs"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        tg_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
        chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
        message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # 'user'/'assistant' для диалога
        created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), server_default=func.now())

    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def upsert_user(session: AsyncSession, tg_user) -> None:
        result = await session.execute(select(User).where(User.tg_user_id == tg_user.id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                tg_user_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            session.add(user)
        else:
            user.username = tg_user.username
            user.first_name = tg_user.first_name
            user.last_name = tg_user.last_name
        await session.commit()

    async def log_message(session: AsyncSession, tg_user_id: int, chat_id: int, msg_id: Optional[int], text_val: Optional[str], role: Optional[str] = None) -> None:
        entry = MessageLog(tg_user_id=tg_user_id, chat_id=chat_id, message_id=msg_id, text=text_val, role=role)
        session.add(entry)
        await session.commit()

    async def get_recent_dialog(session: AsyncSession, tg_user_id: int, limit: int = 12) -> List[Dict[str, str]]:
        # Получаем последние N реплик с ролью
        res = await session.execute(
            select(MessageLog).where(MessageLog.tg_user_id == tg_user_id, MessageLog.role.is_not(None)).order_by(MessageLog.id.desc()).limit(limit)
        )
        rows = list(res.scalars())
        dialog = []
        for r in reversed(rows):
            if r.role in ("user", "assistant") and r.text:
                dialog.append({"role": r.role, "content": r.text})
        return dialog

except Exception:
    # Fallback: in-memory
    SQLA_AVAILABLE = False
    _users: Dict[int, Dict[str, Any]] = {}
    _messages: List[Dict[str, Any]] = []
    _dialog_memory: Dict[int, deque] = defaultdict(lambda: deque(maxlen=20))
    _lock = asyncio.Lock()

    async def upsert_user(session, tg_user) -> None:
        async with _lock:
            _users[tg_user.id] = {
                "tg_user_id": tg_user.id,
                "username": tg_user.username,
                "first_name": tg_user.first_name,
                "last_name": tg_user.last_name,
            }

    async def log_message(session, tg_user_id: int, chat_id: int, msg_id: Optional[int], text_val: Optional[str], role: Optional[str] = None) -> None:
        async with _lock:
            _messages.append(
                {
                    "tg_user_id": tg_user_id,
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": text_val,
                    "role": role,
                    "created_at": time.time(),
                }
            )
            if role in ("user", "assistant") and text_val:
                dq = _dialog_memory[tg_user_id]
                dq.append({"role": role, "content": text_val})

    async def get_recent_dialog(session, tg_user_id: int, limit: int = 12) -> List[Dict[str, str]]:
        async with _lock:
            dq = _dialog_memory[tg_user_id]
            # вернём последние limit
            return list(dq)[-limit:]

# --- Простая антиспам/Rate Limit логика (in-memory) ---
RATE_LIMIT_WINDOW_SEC = 3
RATE_LIMIT_MAX_MESSAGES = 8
_user_messages_window: Dict[int, deque] = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX_MESSAGES))

# --- Помощники AI ---
async def ai_chat_text(user_id: int, user_text: str) -> str:
    """Текстовый диалог с GPT-4o."""
    if not OPENAI_ENABLED or not openai_client:
        return "AI временно недоступен. Повторите позже."

    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    # Добавим историю
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            history = await get_recent_dialog(session, user_id, limit=12)
    else:
        history = await get_recent_dialog(None, user_id, limit=12)
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        resp = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=OPENAI_TEMP,
            max_tokens=OPENAI_MAX_TOKENS,
        )
        reply = resp.choices[0].message.content or "..."
        return reply.strip()
    except Exception as e:
        logger.exception("OpenAI chat error: %s", e)
        return "Извините, сейчас я не могу ответить. Попробуйте позже."

async def ai_chat_vision(user_id: int, user_text: Optional[str], image_urls: List[str]) -> str:
    """Мультимодальный вход (текст+картинка) для GPT-4o."""
    if not OPENAI_ENABLED or not openai_client:
        return "AI временно недоступен. Повторите позже."

    # content как список блоков
    user_content: List[Dict[str, Any]] = []
    if user_text:
        user_content.append({"type": "text", "text": user_text})
    for url in image_urls:
        user_content.append({"type": "image_url", "image_url": {"url": url}})

    messages = [{"role": "system", "content": AI_SYSTEM_PROMPT}]
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            history = await get_recent_dialog(session, user_id, limit=8)
    else:
        history = await get_recent_dialog(None, user_id, limit=8)
    messages.extend(history)
    messages.append({"role": "user", "content": user_content})

    try:
        resp = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=OPENAI_TEMP,
            max_tokens=OPENAI_MAX_TOKENS,
        )
        reply = resp.choices[0].message.content or "..."
        return reply.strip()
    except Exception as e:
        logger.exception("OpenAI vision error: %s", e)
        return "Извините, сейчас я не могу обработать изображение. Попробуйте позже."

async def transcribe_voice(file_bytes: bytes, filename: str = "voice.ogg") -> Optional[str]:
    """Распознавание голоса (Whisper). Возвращает текст или None."""
    if not OPENAI_ENABLED or not openai_client or not OPENAI_ENABLE_VOICE:
        return None
    try:
        # Сохраняем во временный файл для передачи в OpenAI
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        try:
            # В openai v1.x:
            with open(tmp_path, "rb") as f:
                resp = await openai_client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                )
            text = getattr(resp, "text", None)
            return text
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception as e:
        logger.exception("OpenAI transcription error: %s", e)
        return None

# --- Handlers ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user)
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/start", role="user")
    else:
        await upsert_user(None, update.effective_user)
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/start", role="user")

    reply = (
        f"Привет, {update.effective_user.first_name or 'друг'}! 👋\n"
        f"Я — универсальный GPT‑4o бот. Понимаю текст, фото (с описанием) и голосовые сообщения.\n"
        f"Отправь мне сообщение или /help для справки."
    )
    await update.message.reply_text(reply)
    # Лог ответа
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, None, reply, role="assistant")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, None, reply, role="assistant")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    txt = (
        "Я могу:\n"
        "• Отвечать на ваши вопросы (GPT‑4o)\n"
        "• Понимать фото (пришлите изображение с подписью)\n"
        "• Распознавать голос (пришлите voice)\n\n"
        "Команды:\n"
        "/start — начать\n"
        "/help — помощь\n"
        "/status — статус\n"
        "/stats — статистика\n"
    )
    await update.message.reply_text(txt)
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/help", role="user")
            await log_message(session, update.effective_user.id, update.effective_chat.id, None, txt, role="assistant")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/help", role="user")
        await log_message(None, update.effective_user.id, update.effective_chat.id, None, txt, role="assistant")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    msg = f"✅ Бот работает. AI: {'включен' if OPENAI_ENABLED else 'выключен'}."
    await update.message.reply_text(msg)
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/status", role="user")
            await log_message(session, update.effective_user.id, update.effective_chat.id, None, msg, role="assistant")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/status", role="user")
        await log_message(None, update.effective_user.id, update.effective_chat.id, None, msg, role="assistant")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if SQLA_AVAILABLE:
        from sqlalchemy import func as sa_func
        async with SessionLocal() as session:
            users_cnt = (await session.execute(select(sa_func.count()).select_from(User))).scalar_one()
            msgs_cnt = (await session.execute(select(sa_func.count()).select_from(MessageLog))).scalar_one()
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/stats", role="user")
        txt = f"Статистика: пользователей {users_cnt}, сообщений {msgs_cnt}"
        await update.message.reply_text(txt)
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, None, txt, role="assistant")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/stats", role="user")
        txt = "Статистика (in-memory). Для постоянной истории подключите БД."
        await update.message.reply_text(txt)
        await log_message(None, update.effective_user.id, update.effective_chat.id, None, txt, role="assistant")

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    uid = update.effective_user.id
    now = time.time()
    window = _user_messages_window[uid]
    window.append(now)
    while window and now - window[0] > RATE_LIMIT_WINDOW_SEC:
        window.popleft()
    if len(window) >= RATE_LIMIT_MAX_MESSAGES:
        return

    user_text = update.message.text.strip()
    # Лог входа
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user)
            await log_message(session, uid, update.effective_chat.id, update.message.message_id, user_text, role="user")
    else:
        await upsert_user(None, update.effective_user)
        await log_message(None, uid, update.effective_chat.id, update.message.message_id, user_text, role="user")

    # GPT-4o ответ
    reply = await ai_chat_text(uid, user_text)
    await update.message.reply_text(reply)

    # Лог ответа
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, uid, update.effective_chat.id, None, reply, role="assistant")
    else:
        await log_message(None, uid, update.effective_chat.id, None, reply, role="assistant")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.photo:
        return
    uid = update.effective_user.id
    photos = update.message.photo
    caption = (update.message.caption or "").strip()
    # Берём самое большое фото
    largest = photos[-1]
    file = await context.bot.get_file(largest.file_id)
    # Строим публичный URL файла
    image_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

    # Лог входа
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user)
            await log_message(session, uid, update.effective_chat.id, update.message.message_id, f"[photo] {caption}", role="user")
    else:
        await upsert_user(None, update.effective_user)
        await log_message(None, uid, update.effective_chat.id, update.message.message_id, f"[photo] {caption}", role="user")

    reply = await ai_chat_vision(uid, caption if caption else "Опиши картинку.", [image_url])
    await update.message.reply_text(reply)

    # Лог ответа
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, uid, update.effective_chat.id, None, reply, role="assistant")
    else:
        await log_message(None, uid, update.effective_chat.id, None, reply, role="assistant")

async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OPENAI_ENABLE_VOICE:
        return
    if not update.message or not update.message.voice:
        return
    uid = update.effective_user.id
    voice = update.message.voice
    tgf = await context.bot.get_file(voice.file_id)
    # Скачиваем байты голоса
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{tgf.file_path}"
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(file_url)
            resp.raise_for_status()
            voice_bytes = resp.content
    except Exception as e:
        logger.exception("Download voice error: %s", e)
        await update.message.reply_text("Не удалось скачать голосовое сообщение.")
        return

    # Лог входа
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user)
            await log_message(session, uid, update.effective_chat.id, update.message.message_id, "[voice]", role="user")
    else:
        await upsert_user(None, update.effective_user)
        await log_message(None, uid, update.effective_chat.id, update.message.message_id, "[voice]", role="user")

    transcript = await transcribe_voice(voice_bytes, filename="voice.ogg")
    if not transcript:
        await update.message.reply_text("Не удалось распознать голос. Попробуйте ещё раз.")
        return

    # Диалог с GPT по расшифровке
    reply = await ai_chat_text(uid, transcript)
    await update.message.reply_text(reply)

    # Лог ответа
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, uid, update.effective_chat.id, None, reply, role="assistant")
    else:
        await log_message(None, uid, update.effective_chat.id, None, reply, role="assistant")

async def error_handler(update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("PTB error: %s", repr(context.error), exc_info=True)

def build_ptb_application(token: str) -> Application:
    app = (
        ApplicationBuilder()
        .token(token)
        .concurrent_updates(True)
        .build()
    )
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)
    return app

# --- Безопасность webhook ---
TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

def verify_secret_token(req: Request) -> None:
    recv = req.headers.get(TELEGRAM_SECRET_HEADER)
    expected = CURRENT_WEBHOOK_SECRET
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Webhook not initialized")
    if recv != expected:
        logger.warning("Invalid webhook secret token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

def ip_in_ranges(ip: str, cidrs: List[str]) -> bool:
    try:
        ip_addr = ipaddress.ip_address(ip)
    except Exception:
        return False
    for cidr in cidrs:
        try:
            if ip_addr in ipaddress.ip_network(cidr.strip()):
                return True
        except Exception:
            continue
    return False

def verify_ip_allowlist(req: Request) -> None:
    if not ENABLE_IP_ALLOWLIST:
        return
    ranges = [c for c in TELEGRAM_IP_RANGES.split(",") if c.strip()]
    if not ranges:
        return
    client_ip = req.client.host if req.client else None
    if not client_ip or not ip_in_ranges(client_ip, ranges):
        logger.warning("Request IP not in allowlist: %s", client_ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

async def ensure_payload_size(req: Request):
    cl = req.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_TELEGRAM_PAYLOAD_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
        except ValueError:
            pass
    body = await req.body()
    if len(body) > MAX_TELEGRAM_PAYLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
    req._body = body  # Starlette private API

# --- Lifespan: инициализация и завершение ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global application, bot, CURRENT_WEBHOOK_SECRET, openai_client

    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN (или BOT_TOKEN) is not set")
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL (или BASE_URL) is not set")

    # Инициализируем секрет (env или генерация)
    if TELEGRAM_WEBHOOK_SECRET_ENV:
        CURRENT_WEBHOOK_SECRET = TELEGRAM_WEBHOOK_SECRET_ENV
    else:
        CURRENT_WEBHOOK_SECRET = _generate_secret(48)

    # OpenAI клиент
    if OPENAI_ENABLED:
        try:
            openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=60.0)
            logger.info("OpenAI client initialized with model %s", OPENAI_MODEL)
        except Exception:
            openai_client = None
            logger.exception("Failed to initialize OpenAI client")

    # 1) БД
    if SQLA_AVAILABLE:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        except Exception:
            logger.exception("Failed to create DB schema")

    # 2) PTB Application
    application = build_ptb_application(TELEGRAM_TOKEN)
    await application.initialize()
    await application.start()
    bot = application.bot

    # 3) Команды и вебхук
    try:
        commands = [
            BotCommand("start", "Начать работу"),
            BotCommand("help", "Помощь"),
            BotCommand("status", "Статус сервиса"),
            BotCommand("stats", "Базовая статистика"),
        ]
        await bot.set_my_commands(commands)
        allowed_updates = [x.strip() for x in TELEGRAM_ALLOWED_UPDATES.split(",") if x.strip()]
        await bot.delete_webhook(drop_pending_updates=TELEGRAM_DROP_PENDING_UPDATES)
        await bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=CURRENT_WEBHOOK_SECRET,
            allowed_updates=allowed_updates,
            max_connections=TELEGRAM_MAX_CONNECTIONS,
        )
        logger.info("Webhook set to %s", WEBHOOK_URL)
    except Exception as e:
        logger.exception("Failed to set webhook: %s", e)
        raise

    try:
        yield
    finally:
        try:
            if bot:
                await bot.delete_webhook(drop_pending_updates=False)
                logger.info("✅ Webhook удалён при остановке")
        except Exception:
            logger.exception("Failed to delete webhook on shutdown")
        try:
            if application:
                await application.stop()
                await application.shutdown()
        except Exception:
            logger.exception("Failed to shutdown PTB application")
        if SQLA_AVAILABLE:
            try:
                await engine.dispose()
            except Exception:
                logger.exception("Failed to dispose DB engine")

# --- FastAPI app и middleware ---
app = FastAPI(
    title="Telegram Bot API (GPT-4o)",
    version="1.1.0",
    description="Telegram GPT‑4o bot on FastAPI (webhook).",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware, header_name=CORRELATION_ID_HEADER)
app.add_middleware(GZipMiddleware, minimum_size=512)
_allowed_hosts = [h.strip() for h in ALLOWED_HOSTS.split(",")] if ALLOWED_HOSTS else ["*"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)

# --- Health / root ---
@app.get("/health/live")
async def liveness():
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness():
    ok_db = True
    ok_bot = True
    if SQLA_AVAILABLE:
        try:
            async with engine.connect() as conn:
                await conn.execute(sql_text("SELECT 1"))
        except Exception:
            ok_db = False
    try:
        me = await bot.get_me() if bot else None
        ok_bot = me is not None
    except Exception:
        ok_bot = False
    status_code = status.HTTP_200_OK if ok_db and ok_bot else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        content=json.dumps({"db": ok_db, "bot": ok_bot, "status": "ready" if ok_db and ok_bot else "not_ready"}),
        media_type="application/json",
        status_code=status_code,
    )

@app.get("/")
async def root():
    return {"message": "Telegram GPT‑4o Bot is running", "webhook": WEBHOOK_URL, "ai": "enabled" if OPENAI_ENABLED else "disabled"}

# --- Основной webhook ---
@app.post("/telegram")
async def telegram_webhook(request: Request):
    verify_secret_token(request)
    verify_ip_allowlist(request)
    await ensure_payload_size(request)

    ct = request.headers.get("content-type", "")
    if "application/json" not in ct:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported content-type")

    try:
        body = request._body if hasattr(request, "_body") else await request.body()
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    try:
        upd = Update.de_json(data, bot)
        if upd is None:
            logger.warning("Received invalid Update payload")
            return Response(content='{"ok":false}', media_type="application/json", status_code=status.HTTP_200_OK)
        await application.process_update(upd)
        return Response(content='{"ok":true}', media_type="application/json", status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Error processing update: %s", e)
        return Response(content='{"ok":true}', media_type="application/json", status_code=status.HTTP_200_OK)

# --- Локальный запуск ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
