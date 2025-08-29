# bot.py
# Production-ready Telegram бот на FastAPI (webhook) с:
# - Lifespan (инициализация/завершение) и корректным жизненным циклом PTB Application
# - Secure webhook: X-Telegram-Bot-Api-Secret-Token (автогенерация при отсутствии)
# - Middleware correlation-id (graceful fallback), GZip, TrustedHost
# - Асинхронная БД через SQLAlchemy 2.0 (graceful fallback на in-memory)
# - Rate limit, health-check, базовые команды, обработка текста

import os
import json
import time
import asyncio
import ipaddress
import logging
import secrets
import string
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

# --- Настройка окружения ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
# Если не задан, секрет будет сгенерирован на старте и сохранён в CURRENT_WEBHOOK_SECRET
TELEGRAM_WEBHOOK_SECRET_ENV = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()  # 1..256, A-Z a-z 0-9 _ -

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*")
TELEGRAM_ALLOWED_UPDATES = os.getenv("TELEGRAM_ALLOWED_UPDATES", "message,callback_query")
TELEGRAM_DROP_PENDING_UPDATES = os.getenv("TELEGRAM_DROP_PENDING_UPDATES", "true").lower() == "true"
TELEGRAM_MAX_CONNECTIONS = int(os.getenv("TELEGRAM_MAX_CONNECTIONS", "40"))
ENABLE_IP_ALLOWLIST = os.getenv("ENABLE_IP_ALLOWLIST", "false").lower() == "true"
TELEGRAM_IP_RANGES = os.getenv("TELEGRAM_IP_RANGES", "")  # "149.154.160.0/20,91.108.4.0/22"
CORRELATION_ID_HEADER = os.getenv("CORRELATION_ID_HEADER", "X-Request-ID")
MAX_TELEGRAM_PAYLOAD_BYTES = int(os.getenv("MAX_TELEGRAM_PAYLOAD_BYTES", "1048576"))

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

def _generate_secret(length: int = 32) -> str:
    # Разрешённые символы по требованиям Telegram (A-Z a-z 0-9 _ -)
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))

# --- SQLAlchemy (опционально), fallback на in-memory если модуля нет ---
try:
    from sqlalchemy import String, Integer, BigInteger, Text, DateTime, func, select, text
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

    async def log_message(session: AsyncSession, tg_user_id: int, chat_id: int, msg_id: Optional[int], text_val: Optional[str]) -> None:
        entry = MessageLog(tg_user_id=tg_user_id, chat_id=chat_id, message_id=msg_id, text=text_val)
        session.add(entry)
        await session.commit()

    async def count_users(session: AsyncSession) -> int:
        res = await session.execute(select(func.count()).select_from(User))
        return int(res.scalar_one() or 0)

    async def count_messages(session: AsyncSession) -> int:
        res = await session.execute(select(func.count()).select_from(MessageLog))
        return int(res.scalar_one() or 0)

except Exception:
    # Fallback: in-memory
    SQLA_AVAILABLE = False
    _users: Dict[int, Dict[str, Any]] = {}
    _messages: List[Dict[str, Any]] = []
    _lock = asyncio.Lock()

    async def upsert_user(session, tg_user) -> None:
        async with _lock:
            _users[tg_user.id] = {
                "tg_user_id": tg_user.id,
                "username": tg_user.username,
                "first_name": tg_user.first_name,
                "last_name": tg_user.last_name,
            }

    async def log_message(session, tg_user_id: int, chat_id: int, msg_id: Optional[int], text_val: Optional[str]) -> None:
        async with _lock:
            _messages.append(
                {
                    "tg_user_id": tg_user_id,
                    "chat_id": chat_id,
                    "message_id": msg_id,
                    "text": text_val,
                    "created_at": time.time(),
                }
            )

    async def count_users(session=None) -> int:
        return len(_users)

    async def count_messages(session=None) -> int:
        return len(_messages)

# --- Простая антиспам/Rate Limit логика (in-memory) ---
RATE_LIMIT_WINDOW_SEC = 3
RATE_LIMIT_MAX_MESSAGES = 8
_user_messages_window: Dict[int, deque] = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX_MESSAGES))

# --- Handlers ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user)
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/start")
    else:
        await upsert_user(None, update.effective_user)
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/start")

    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name or 'друг'}! 👋\nНаберите /help для списка команд."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/help")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/help")

    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — начать\n"
        "/help — помощь\n"
        "/status — статус сервиса\n"
        "/stats — базовая статистика\n"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/status")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/status")

    await update.message.reply_text("✅ Бот и API работают штатно.")

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            users_cnt = await count_users(session)
            msgs_cnt = await count_messages(session)
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/stats")
        await update.message.reply_text(f"Статистика: пользователей {users_cnt}, сообщений {msgs_cnt}")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/stats")
        await update.message.reply_text(f"Статистика (in-memory): пользователей ~{await count_users()}, сообщений ~{await count_messages()}")

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

    text_val = update.message.text
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user)
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, text_val)
    else:
        await upsert_user(None, update.effective_user)
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, text_val)

    lower = text_val.lower()
    if "привет" in lower:
        await update.message.reply_text(f"Привет, {update.effective_user.first_name or ''}! 😊")
    elif "как дела" in lower:
        await update.message.reply_text("У меня отлично! А у тебя?")
    else:
        await update.message.reply_text("Я получил твоё сообщение. Отправь /help для списка команд.")

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)
    return app

# --- Безопасность webhook ---
TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"

def verify_secret_token(req: Request) -> None:
    recv = req.headers.get(TELEGRAM_SECRET_HEADER)
    expected = CURRENT_WEBHOOK_SECRET
    if not expected:
        # Если секрет не установлен (не должно случаться после старта), пропустим, но залогируем
        logger.warning("Webhook secret not initialized at verification step")
        return
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

def verify_ip_allow<span class="cursor">█</span>
