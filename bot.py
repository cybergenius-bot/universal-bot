import os
import json
import time
import asyncio
import ipaddress
import logging
import secrets
import string
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any, Union
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
TELEGRAM_IP_RANGES = os.getenv("TELEGRAM_IP_RANGES", "")
CORRELATION_ID_HEADER = os.getenv("CORRELATION_ID_HEADER", "X-Request-ID")
MAX_TELEGRAM_PAYLOAD_BYTES = int(os.getenv("MAX_TELEGRAM_PAYLOAD_BYTES", "1048576"))

# OpenAI (GPT‑4o)
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o").strip()  # по запросу — gpt-4o; можно сменить на gpt-4o-mini
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.4"))
OPENAI_MAX_HISTORY = int(os.getenv("OPENAI_MAX_HISTORY", "8"))  # пар сообщений в памяти
DISABLE_RATE_LIMIT = os.getenv("DISABLE_RATE_LIMIT", "false").lower() == "true"

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

application: Optional[Application] = None
bot: Optional[Bot] = None

# Текущий секрет вебхука (из env или сгенерированный на старте)
CURRENT_WEBHOOK_SECRET: Optional[str] = None

def _generate_secret(length: int = 48) -> str:
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))

# --- SQLAlchemy (опционально), fallback на in-memory ---
try:
    from sqlalchemy import String, Integer, BigInteger, Text, DateTime, func, select, text as sa_text
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

# --- OpenAI клиент ---
_openai_client = None
def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        from openai import OpenAI  # lazy import
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client

# --- Вспомогательные функции ---
TELEGRAM_MAX_MESSAGE_CHARS = 4096
def split_chunks(s: str, size: int = 4000) -> List[str]:
    # режем по границам строк, сохраняя читаемость
    out, cur = [], []
    cur_len = 0
    for line in s.splitlines(keepends=True):
        if cur_len + len(line) > size and cur:
            out.append("".join(cur))
            cur, cur_len = [line], len(line)
        else:
            cur.append(line)
            cur_len += len(line)
    if cur:
        out.append("".join(cur))
    # если нет переносов, всё равно гарантируем размер
    final = []
    for chunk in out:
        if len(chunk) <= size:
            final.append(chunk)
        else:
            for i in range(0, len(chunk), size):
                final.append(chunk[i:i+size])
    return final or [""]

def build_system_prompt() -> str:
    return (
        "Ты — универсальный, вежливый и полезный ассистент. "
        "Отвечай кратко и по делу, при необходимости давай пошаговые инструкции. "
        "Если вопрос неясен — уточни. Поддерживай русский язык."
    )

def build_vision_content(text_part: Optional[str], image_url: Optional[str]) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = []
    if text_part:
        content.append({"type": "text", "text": text_part})
    if image_url:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    if not content:
        content.append({"type": "text", "text": "Опиши изображение."})
    return content

async def openai_chat_reply(
    user_text: Optional[str],
    vision_image_url: Optional[str],
    history: List[Dict[str, Union[str, List[Dict[str, Any]]]]],
) -> str:
    """
    history: список сообщений вида:
      {"role":"user","content":"..."} или {"role":"assistant","content":"..."} или для vision content=[{...}]
    """
    client = _get_openai_client()
    sys_prompt = build_system_prompt()

    messages: List[Dict[str, Any]] = [{"role": "system", "content": sys_prompt}]
    # берем только последние OPENAI_MAX_HISTORY пар (user+assistant)
    trimmed = history[-(OPENAI_MAX_HISTORY * 2):] if OPENAI_MAX_HISTORY > 0 else history
    messages.extend(trimmed)

    if vision_image_url:
        messages.append({"role": "user", "content": build_vision_content(user_text or "", vision_image_url)})
    else:
        messages.append({"role": "user", "content": user_text or ""})

    # Вызов Chat Completions (без стриминга — надёжно для Telegram)
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        temperature=OPENAI_TEMPERATURE,
    )
    answer = (resp.choices[0].message.content or "").strip()
    return answer or "Готово."

# --- Rate limit (можно отключить переменной DISABLE_RATE_LIMIT=true) ---
RATE_LIMIT_WINDOW_SEC = 3
RATE_LIMIT_MAX_MESSAGES = 8
_user_messages_window: Dict[int, deque] = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX_MESSAGES))

def rate_limited(user_id: int) -> bool:
    if DISABLE_RATE_LIMIT:
        return False
    now = time.time()
    window = _user_messages_window[user_id]
    window.append(now)
    while window and now - window[0] > RATE_LIMIT_WINDOW_SEC:
        window.popleft()
    return len(window) >= RATE_LIMIT_MAX_MESSAGES

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
        f"Привет, {update.effective_user.first_name or 'друг'}! 👋\n"
        f"Я подключён к GPT‑4o. Просто напиши сообщение или пришли фото с подписью."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    log_text = "/help"
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, log_text)
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, log_text)

    await update.message.reply_text(
        "Я могу:\n"
        "• Отвечать на текстовые вопросы (GPT‑4o)\n"
        "• Понимать изображения (пришлите фото с подписью)\n"
        "• Команды: /start /help /status /stats\n"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/status")
    else:
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/status")

    await update.message.reply_text("✅ Сервис в сети. GPT‑4o подключён." if OPENAI_API_KEY else "⚠️ GPT не настроен (нет OPENAI_API_KEY).")

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
        await update.message.reply_text("Статистика (in-memory).")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Обработка изображений + подписи через GPT‑4o vision
    if not update.message or not update.message.photo:
        return
    if rate_limited(update.effective_user.id):
        return

    caption = update.message.caption or ""
    # берём самое большое фото
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    # прямой URL к файлу Telegram (валиден без подписи)
    image_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file.file_path}"

    # история диалога пользователя (in-memory)
    history: List[Dict[str, Any]] = context.user_data.get("history", [])

    try:
        reply = await openai_chat_reply(user_text=caption, vision_image_url=image_url, history=history)
    except Exception as e:
        logger.exception("OpenAI vision error: %s", e)
        reply = "Извините, не удалось обработать изображение."

    # обновляем историю
    if OPENAI_MAX_HISTORY > 0:
        # добавляем как текстовую запись (не храним сами картинки в истории — только текст подписи)
        history.append({"role": "user", "content": caption})
        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-(OPENAI_MAX_HISTORY * 2):]

    # отправляем с нарезкой
    for chunk in split_chunks(reply, 4000):
        await update.message.reply_text(chunk)

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or (not update.message.text and not update.message.caption):
        return
    if rate_limited(update.effective_user.id):
        return

    text_val = update.message.text or update.message.caption or ""
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user)
            await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, text_val)
    else:
        await upsert_user(None, update.effective_user)
        await log_message(None, update.effective_user.id, update.effective_chat.id, update.message.message_id, text_val)

    # Если есть фото в этом же сообщении — пусть сработает photo_handler (в Telegram caption идёт вместе с фото),
    # здесь обрабатываем «чистый» текст.
    if update.message.photo:
        return

    # История
    history: List[Dict[str, Any]] = context.user_data.get("history", [])
    try:
        reply = await openai_chat_reply(user_text=text_val, vision_image_url=None, history=history)
    except Exception as e:
        logger.exception("OpenAI chat error: %s", e)
        reply = "Извините, сейчас не могу ответить. Попробуйте позже."

    if OPENAI_MAX_HISTORY > 0:
        history.append({"role": "user", "content": text_val})
        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-(OPENAI_MAX_HISTORY * 2):]

    for chunk in split_chunks(reply, 4000):
        await update.message.reply_text(chunk)

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
    # фото с подписью — отдельный хэндлер до текстового
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    # обычный текст
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
    global application, bot, CURRENT_WEBHOOK_SECRET

    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN (или BOT_TOKEN) is not set")
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL (или BASE_URL) is not set")

    if TELEGRAM_WEBHOOK_SECRET_ENV:
        CURRENT_WEBHOOK_SECRET = TELEGRAM_WEBHOOK_SECRET_ENV
    else:
        CURRENT_WEBHOOK_SECRET = _generate_secret()

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
    title="Telegram Bot API (GPT‑4o)",
    version="1.1.0",
    description="Telegram bot on FastAPI + GPT‑4o (webhook).",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware, header_name=CORRELATION_ID_HEADER)
app.add_middleware(GZipMiddleware, minimum_size=512)
_allowed_hosts = [h.strip() for h in ALLOWED_HOSTS.split(",")] if ALLOWED_HOSTS else ["*"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)

# --- Health/Service ---
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
                await conn.execute(sa_text("SELECT 1"))
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
    return {"message": "Telegram Bot is running (GPT‑4o ready)", "webhook": WEBHOOK_URL}

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
