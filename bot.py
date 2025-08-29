import os
import json
import ipaddress
import logging
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from asgi_correlation_id import CorrelationIdMiddleware

from telegram import Update, Bot, BotCommand
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings

from sqlalchemy import String, Integer, BigInteger, Text, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

# -----------------------------
# Конфигурация через переменные окружения (Pydantic Settings)
# -----------------------------
class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    WEBHOOK_URL: str  # Полный HTTPS URL вашего эндпоинта /telegram
    TELEGRAM_WEBHOOK_SECRET: str  # 1..256 символов, только A-Z a-z 0-9 _ -
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"  # Для прод: postgresql+asyncpg://user:pass@host:port/db
    LOG_LEVEL: str = "INFO"
    ALLOWED_HOSTS: str = "*"  # Запятая-разделённый список доменов или *
    TELEGRAM_ALLOWED_UPDATES: str = "message,callback_query"
    TELEGRAM_DROP_PENDING_UPDATES: bool = True
    TELEGRAM_MAX_CONNECTIONS: int = 40  # 1..100
    ENABLE_IP_ALLOWLIST: bool = False
    # Список сетей в формате CIDR через запятую, например:
    # "149.154.160.0/20,91.108.4.0/22" (опционально, Telegram IP-диапазоны могут изменяться)
    TELEGRAM_IP_RANGES: str = ""

    # Correlation-ID заголовок для логов
    CORRELATION_ID_HEADER: str = "X-Request-ID"

    # Ограничение размера тела запроса (байты) для /telegram, чтобы защититься от перегрузки
    MAX_TELEGRAM_PAYLOAD_BYTES: int = 1024 * 1024  # 1MB

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# -----------------------------
# Логирование с учетом correlation-id
# -----------------------------
LOG_LEVEL_NUM = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=LOG_LEVEL_NUM,
    format="%(asctime)s %(levelname)s [%(name)s] [%(correlation_id)s] %(message)s",
)
logger = logging.getLogger("bot")

# -----------------------------
# SQLAlchemy ORM модели и сессии
# -----------------------------
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


engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# -----------------------------
# Telegram Application и Handlers
# -----------------------------
application: Optional[Application] = None  # PTB Application
bot: Optional[Bot] = None  # Telegram Bot

# Простая антиспам/Rate Limit логика: отсев частых сообщений (in-memory)
# Для настоящего продакшена лучше использовать Redis/Rate limiter.
from collections import defaultdict, deque
import time

RATE_LIMIT_WINDOW_SEC = 3
RATE_LIMIT_MAX_MESSAGES = 8
_user_messages_window: Dict[int, deque] = defaultdict(lambda: deque(maxlen=RATE_LIMIT_MAX_MESSAGES))


async def upsert_user(session: AsyncSession, tg_user) -> None:
    from sqlalchemy import select

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


async def log_message(session: AsyncSession, tg_user_id: int, chat_id: int, msg_id: Optional[int], text: Optional[str]) -> None:
    entry = MessageLog(
        tg_user_id=tg_user_id,
        chat_id=chat_id,
        message_id=msg_id,
        text=text,
    )
    session.add(entry)
    await session.commit()


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    async with SessionLocal() as session:
        await upsert_user(session, update.effective_user)
        await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/start")

    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name or 'друг'}! 👋\n"
        f"Я готов помочь. Наберите /help для списка команд."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    async with SessionLocal() as session:
        await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/help")

    await update.message.reply_text(
        "Доступные команды:\n"
        "/start — начало работы\n"
        "/help — помощь\n"
        "/status — статус сервиса\n"
        "/stats — базовая статистика\n"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    async with SessionLocal() as session:
        await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/status")

    await update.message.reply_text("✅ Бот и API работают штатно.")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    from sqlalchemy import select, func as sa_func
    async with SessionLocal() as session:
        users_cnt = (await session.execute(sa_func.count(User.id))).scalar()
        msgs_cnt = (await session.execute(sa_func.count(MessageLog.id))).scalar()
        await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, "/stats")

    await update.message.reply_text(f"Статистика:\nПользователей: {users_cnt}\nСообщений: {msgs_cnt}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    # Простейший rate limit per-user в скользящем окне
    uid = update.effective_user.id
    now = time.time()
    window = _user_messages_window[uid]
    window.append(now)
    while window and now - window[0] > RATE_LIMIT_WINDOW_SEC:
        window.popleft()
    if len(window) >= RATE_LIMIT_MAX_MESSAGES:
        # Мягкий отклик без спама
        return

    text = update.message.text
    async with SessionLocal() as session:
        await upsert_user(session, update.effective_user)
        await log_message(session, update.effective_user.id, update.effective_chat.id, update.message.message_id, text)

    lower = text.lower()
    if "привет" in lower:
        await update.message.reply_text(f"Привет, {update.effective_user.first_name or ''}! 😊")
    elif "как дела" in lower:
        await update.message.reply_text("У меня отлично! А у тебя?")
    else:
        await update.message.reply_text("Я получил твоё сообщение. Отправь /help для списка команд.")


async def error_handler(update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
    # Централизованная обработка ошибок PTB
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


# -----------------------------
# Безопасность webhook: заголовок и (опц.) IP-аллоулист
# -----------------------------
TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"  # Согласно Bot API setWebhook secret_token


def verify_secret_token(req: Request) -> None:
    recv = req.headers.get(TELEGRAM_SECRET_HEADER)
    expected = settings.TELEGRAM_WEBHOOK_SECRET
    if not expected:
        # Если секрет не настроен — это существенный риск, лучше не продолжать
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Webhook secret is not configured")
    if recv != expected:
        logger.warning("Invalid secret token on webhook")
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
    if not settings.ENABLE_IP_ALLOWLIST:
        return
    ranges = [c for c in settings.TELEGRAM_IP_RANGES.split(",") if c.strip()]
    if not ranges:
        return
    client_ip = req.client.host if req.client else None
    if not client_ip or not ip_in_ranges(client_ip, ranges):
        logger.warning("Request IP not in allowlist: %s", client_ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


# -----------------------------
# Валидация размера тела запроса
# -----------------------------
class TelegramWebhookPayload(BaseModel):
    # Для легкой первичной валидации размера и формата. Полная Deserialize идёт через Update.de_json
    update_id: Optional[int] = Field(default=None)


async def ensure_payload_size(req: Request):
    cl = req.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > settings.MAX_TELEGRAM_PAYLOAD_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
        except ValueError:
            pass  # игнорируем некорректный header и проверим на уровне реального чтения
    # Дополнительная защита при чтении
    body = await req.body()
    if len(body) > settings.MAX_TELEGRAM_PAYLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
    # Возвращаем обратно в stream для дальнейшего чтения
    req._body = body  # Starlette private API — безопасно в пределах одного запроса


# -----------------------------
# Lifespan: инициализация и завершение
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global application, bot
    # 1) Поднять БД (создать таблицы)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2) Собрать и инициализировать PTB Application один раз
    application = build_ptb_application(settings.TELEGRAM_TOKEN)
    await application.initialize()  # Требуется до process_update
    await application.start()       # Запускает фоновые задачи job_queue/persistence и т.п.
    bot = application.bot

    # 3) Настроить команды и вебхук
    try:
        commands = [
            BotCommand("start", "Начать работу"),
            BotCommand("help", "Помощь"),
            BotCommand("status", "Статус сервиса"),
            BotCommand("stats", "Базовая статистика"),
        ]
        await bot.set_my_commands(commands)

        allowed_updates = [x.strip() for x in settings.TELEGRAM_ALLOWED_UPDATES.split(",") if x.strip()]
        await bot.delete_webhook(drop_pending_updates=settings.TELEGRAM_DROP_PENDING_UPDATES)
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
            secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            allowed_updates=allowed_updates,
            max_connections=settings.TELEGRAM_MAX_CONNECTIONS,
        )
        logger.info("Webhook set to %s", settings.WEBHOOK_URL)
    except Exception as e:
        logger.exception("Failed to set webhook: %s", e)
        # Важно: если вебхук не поставился, дальнейший приём апдейтов невозможен.
        # Можно падать, чтобы оркестратор рестартовал.
        raise

    try:
        yield
    finally:
        # Снятие вебхука перед остановкой
        try:
            if bot:
                await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            logger.exception("Failed to delete webhook on shutdown")

        # Остановить PTB Application
        try:
            if application:
                await application.stop()
                await application.shutdown()
        except Exception:
            logger.exception("Failed to shutdown PTB application")

        # Закрыть коннекты к БД
        try:
            await engine.dispose()
        except Exception:
            logger.exception("Failed to dispose DB engine")


# -----------------------------
# FastAPI приложение и middleware
# -----------------------------
app = FastAPI(
    title="Telegram Bot API",
    version="1.0.0",
    description="Production-ready Telegram bot on FastAPI (webhook).",
    lifespan=lifespan,  # Lifespan вместо @on_event start/stop
)

# Корреляция логов по запросу
app.add_middleware(CorrelationIdMiddleware, header_name=settings.CORRELATION_ID_HEADER)
# Сжатие ответов
app.add_middleware(GZipMiddleware, minimum_size=512)

# Trusted hosts (хорошо для prod, замените '*' на свой домен)
allowed_hosts = [h.strip() for h in settings.ALLOWED_HOSTS.split(",")] if settings.ALLOWED_HOSTS else ["*"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


# -----------------------------
# Health-check endpoints
# -----------------------------
@app.get("/health/live")
async def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness():
    # Проверим БД и способность обращаться к Telegram API getMe
    ok_db = True
    ok_bot = True
    try:
        async with engine.connect() as conn:
            await conn.execute(func.now())  # простая проверка
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


# -----------------------------
# Корневой эндпоинт
# -----------------------------
@app.get("/")
async def root():
    return {"message": "Telegram Bot is running", "webhook": settings.WEBHOOK_URL}


# -----------------------------
# Основной webhook эндпоинт
# -----------------------------
@app.post("/telegram")
async def telegram_webhook(request: Request):
    # Безопасность: проверка секретного заголовка и (опц.) IP
    verify_secret_token(request)  # X-Telegram-Bot-Api-Secret-Token
    verify_ip_allowlist(request)  # опционально

    # Защита по размеру тела
    await ensure_payload_size(request)

    # Дополнительно: проверка content-type
    ct = request.headers.get("content-type", "")
    if "application/json" not in ct:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported content-type")

    try:
        # Используем тело, заранее считанное ensure_payload_size
        body = request._body if hasattr(request, "_body") else await request.body()
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Лёгкая предвалидация (необязательная)
    try:
        TelegramWebhookPayload.model_validate(data, strict=False)
    except ValidationError:
        # Не падаем жёстко — Telegram может прислать любые типы апдейтов
        pass

    # Преобразование в Update и передача PTB-приложению
    try:
        upd = Update.de_json(data, bot)
        if upd is None:
            logger.warning("Received invalid Update payload")
            return Response(content='{"ok":false}', media_type="application/json", status_code=status.HTTP_200_OK)

        # ВАЖНО: process_update требует предварительной initialize/start приложения
        await application.process_update(upd)
        # Всегда отвечаем 200 ОК, чтобы Telegram не ретраил
        return Response(content='{"ok":true}', media_type="application/json", status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Error processing update: %s", e)
        # Отвечаем 200, чтобы Telegram не засыпал нас ретраями
        return Response(content='{"ok":true}', media_type="application/json", status_code=status.HTTP_200_OK)


# -----------------------------
# Локальный запуск
# -----------------------------
if __name__ == "__main__":
    import uvicorn

    # В продакшене поднимайте через процесс-менеджер (gunicorn/uvicorn workers), тут — для локального запуска
    uvicorn.run("bot:app", host="0.0.0.0", port=8000, reload=True)
