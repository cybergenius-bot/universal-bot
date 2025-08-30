import os
import io
import json
import time
import base64
import asyncio
import ipaddress
import logging
import secrets
import string
import tempfile
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from collections import defaultdict, deque
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta

import httpx
from fastapi import FastAPI, Request, Response, HTTPException, status, APIRouter
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

# --- Correlation-ID middleware (graceful fallback) ---
try:
    from asgi_correlation_id import CorrelationIdMiddleware, CorrelationIdFilter  # type: ignore
except Exception:
    class CorrelationIdMiddleware:  # no-op
        def __init__(self, app, header_name: str = "X-Request-ID", *args, **kwargs):
            self.app = app
        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)
    class CorrelationIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if not hasattr(record, "correlation_id"):
                record.correlation_id = "-"
            return True

# --- ENV ---
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
BASE_URL = (os.getenv("BASE_URL") or "").strip().rstrip("/")
WEBHOOK_URL = (os.getenv("WEBHOOK_URL") or (f"{BASE_URL}/telegram" if BASE_URL else "")).strip()
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or BASE_URL).strip().rstrip("/")

TELEGRAM_WEBHOOK_SECRET = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

TELEGRAM_ALLOWED_UPDATES = os.getenv("TELEGRAM_ALLOWED_UPDATES", "message,callback_query")
TELEGRAM_DROP_PENDING_UPDATES = os.getenv("TELEGRAM_DROP_PENDING_UPDATES", "true").lower() == "true"
TELEGRAM_MAX_CONNECTIONS = int(os.getenv("TELEGRAM_MAX_CONNECTIONS", "40"))
MAX_TELEGRAM_PAYLOAD_BYTES = int(os.getenv("MAX_TELEGRAM_PAYLOAD_BYTES", "1048576"))

ENABLE_IP_ALLOWLIST = os.getenv("ENABLE_IP_ALLOWLIST", "false").lower() == "true"
TELEGRAM_IP_RANGES = os.getenv("TELEGRAM_IP_RANGES", "")

# OpenAI
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4o-mini").strip()
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.6"))
OPENAI_MAX_HISTORY = int(os.getenv("OPENAI_MAX_HISTORY", "8"))

# Квоты/планы
PLAN_FREE_QUESTS = int(os.getenv("PLAN_FREE_QUESTS", "5"))
PLAN_STARTER_PRICE = int(os.getenv("PLAN_STARTER_PRICE", "10"))
PLAN_STARTER_QUOTA = int(os.getenv("PLAN_STARTER_QUOTA", "20"))
PLAN_PRO_PRICE = int(os.getenv("PLAN_PRO_PRICE", "30"))
PLAN_PRO_QUOTA = int(os.getenv("PLAN_PRO_QUOTA", "200"))
PLAN_UNLIM_PRICE = int(os.getenv("PLAN_UNLIM_PRICE", "50"))
PLAN_UNLIM_MONTHS = int(os.getenv("PLAN_UNLIM_MONTHS", "1"))

# PayPal
PAYPAL_BASE = os.getenv("PAYPAL_BASE", "https://api-m.sandbox.paypal.com").rstrip("/")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "").strip()
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET", "").strip()
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()

# DB
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")

# --- Logging ---
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] [%(correlation_id)s] %(message)s",
)
for _h in logging.getLogger().handlers:
    _h.addFilter(CorrelationIdFilter())
logger = logging.getLogger("bot")

# --- Telegram (PTB) ---
from telegram import Update, Bot, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

application: Optional[Application] = None
bot: Optional[Bot] = None

TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
CURRENT_WEBHOOK_SECRET: Optional[str] = None

def _generate_secret(length: int = 48) -> str:
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))

# --- SQLAlchemy models (с фолбэком на in-memory) ---
try:
    from sqlalchemy import (
        String, Integer, BigInteger, Text, DateTime, Boolean,
        select, func, text as sa_text,
    )
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    SQLA_AVAILABLE = True

    class Base(DeclarativeBase):
        pass

    class User(Base):
        __tablename__ = "users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
        username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
        first_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
        last_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
        referrer_tg_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    class MessageLog(Base):
        __tablename__ = "message_logs"
        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
        chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
        message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
        text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    class Subscription(Base):
        __tablename__ = "subscriptions"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
        plan: Mapped[str] = mapped_column(String(32))  # FREE/STARTER/PRO/UNLIM
        expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
        active: Mapped[bool] = mapped_column(Boolean, default=True)

    class UsageCounter(Base):
        __tablename__ = "usage_counters"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
        period: Mapped[str] = mapped_column(String(16))  # lifetime / month
        used: Mapped[int] = mapped_column(Integer, default=0)
        reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    class Payment(Base):
        __tablename__ = "payments"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        tg_id: Mapped[int] = mapped_column(BigInteger, index=True)
        chat_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
        platform: Mapped[str] = mapped_column(String(16))  # 'paypal'
        plan: Mapped[str] = mapped_column(String(32))
        amount: Mapped[int] = mapped_column(Integer)
        status: Mapped[str] = mapped_column(String(16))  # created/approved/captured/failed
        external_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # PayPal order id
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def upsert_user(session: AsyncSession, tg_user, referrer: Optional[int] = None) -> None:
        res = await session.execute(select(User).where(User.tg_id == tg_user.id))
        u = res.scalar_one_or_none()
        if not u:
            u = User(
                tg_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
                referrer_tg_id=referrer,
            )
            session.add(u)
            # Free-план по умолчанию
            sub = Subscription(tg_id=tg_user.id, plan="FREE", expires_at=None, active=True)
            ctr = UsageCounter(tg_id=tg_user.id, period="lifetime", used=0, reset_at=None)
            session.add_all([sub, ctr])
        else:
            u.username = tg_user.username
            u.first_name = tg_user.first_name
            u.last_name = tg_user.last_name
        await session.commit()

    async def log_message(session: AsyncSession, tg_id: int, chat_id: int, msg_id: Optional[int], text_val: Optional[str]):
        entry = MessageLog(tg_id=tg_id, chat_id=chat_id, message_id=msg_id, text=text_val)
        session.add(entry)
        await session.commit()

    async def count_users(session: AsyncSession) -> int:
        r = await session.execute(select(func.count()).select_from(User))
        return int(r.scalar_one() or 0)

    async def count_messages(session: AsyncSession) -> int:
        r = await session.execute(select(func.count()).select_from(MessageLog))
        return int(r.scalar_one() or 0)

    async def get_usage_and_plan(session: AsyncSession, tg_id: int):
        sub = (await session.execute(select(Subscription).where(Subscription.tg_id == tg_id, Subscription.active == True))).scalar_one_or_none()
        ctr = (await session.execute(select(UsageCounter).where(UsageCounter.tg_id == tg_id))).scalar_one_or_none()
        return sub, ctr

    def plan_limits(plan: str) -> tuple[Optional[int], str, Optional[datetime]]:
        if plan == "FREE":
            return PLAN_FREE_QUESTS, "lifetime", None
        if plan == "STARTER":
            return PLAN_STARTER_QUOTA, "lifetime", None
        if plan == "PRO":
            return PLAN_PRO_QUOTA, "lifetime", None
        if plan == "UNLIM":
            return 10**9, "month", (datetime.now(timezone.utc) + relativedelta(months=PLAN_UNLIM_MONTHS))
        return PLAN_FREE_QUESTS, "lifetime", None

    async def increment_usage(session: AsyncSession, tg_id: int) -> tuple[bool, str]:
        sub, ctr = await get_usage_and_plan(session, tg_id)
        if not sub or not ctr:
            return False, "Нет активного плана"
        # истечение UNLIM
        if sub.plan == "UNLIM" and sub.expires_at and datetime.now(timezone.utc) > sub.expires_at:
            sub.active = False
            await session.commit()
            return False, "Подписка UNLIM истекла"
        # сброс помесячного счётчика
        if ctr.period == "month" and ctr.reset_at and datetime.now(timezone.utc) >= ctr.reset_at:
            ctr.used = 0
            ctr.reset_at = datetime.now(timezone.utc) + relativedelta(months=1)
        limit, period, _ = plan_limits(sub.plan)
        if limit is not None and ctr.used >= limit:
            return False, f"Лимит исчерпан для плана {sub.plan}"
        ctr.used += 1
        await session.commit()
        return True, "OK"

    async def activate_plan(session: AsyncSession, tg_id: int, plan: str):
        sub, ctr = await get_usage_and_plan(session, tg_id)
        _, period, expires = plan_limits(plan)
        if not sub:
            sub = Subscription(tg_id=tg_id, plan=plan, expires_at=expires, active=True)
            session.add(sub)
        else:
            sub.plan, sub.expires_at, sub.active = plan, expires, True
        if not ctr:
            ctr = UsageCounter(tg_id=tg_id, period=period, used=0, reset_at=(datetime.now(timezone.utc)+relativedelta(months=1) if period=="month" else None))
            session.add(ctr)
        else:
            ctr.period, ctr.used = period, 0
            ctr.reset_at = (datetime.now(timezone.utc)+relativedelta(months=1) if period=="month" else None)
        await session.commit()

except Exception:
    SQLA_AVAILABLE = False
    engine = None
    SessionLocal = None
    logger.warning("SQLAlchemy not available; running in-memory mode")

# --- OpenAI client ---
_openai_client = None
def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        from openai import OpenAI
        _openai_client = OpenAI(api_key=OPENAI_API_KEY)
    return _openai_client

TELEGRAM_MAX_MESSAGE_CHARS = 4096

def chunk_text(text: str, max_len: int = 3500) -> List[str]:
    chunks = []
    s = text or ""
    while s:
        if len(s) <= max_len:
            chunks.append(s)
            break
        piece = s[:max_len]
        cut = max(piece.rfind("\n"), piece.rfind("."))
        if cut >= int(max_len*0.6):
            chunks.append(s[:cut+1].strip())
            s = s[cut+1:].lstrip()
        else:
            chunks.append(piece)
            s = s[max_len:]
    return chunks or [""]

SYSTEM_PROMPT = (
    "Ты — универсальный ассистент Telegram‑бота: отвечай по‑русски, дружелюбно и по делу. "
    "Генерируй большие ответы при необходимости, но структурируй текст. "
    "Если просят «сторис», сделай 2–4 экрана: цепляющий первый экран, разговорный тон, уместные эмодзи, финальный призыв к действию. "
    "Избегай лишних дисклеймеров."
)

def build_vision_message(caption: str, image_bytes: bytes) -> List[Dict[str, Any]]:
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"
    return [
        {"type": "text", "text": caption or "Опиши изображение и сделай полезные выводы/идеи."},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]

async def llm_chat(user_text: str, history: List[Dict[str, Any]]) -> str:
    client = _get_openai_client()
    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    trimmed = history[-(OPENAI_MAX_HISTORY*2):] if OPENAI_MAX_HISTORY > 0 else history
    messages.extend(trimmed)
    messages.append({"role": "user", "content": user_text})
    loop = asyncio.get_running_loop()
    def _call():
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=OPENAI_TEMPERATURE,
            max_tokens=1200,
        )
        return (resp.choices[0].message.content or "").strip()
    return await loop.run_in_executor(None, _call)

async def llm_vision(caption: str, image_bytes: bytes, history: List[Dict[str, Any]]) -> str:
    client = _get_openai_client()
    messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    trimmed = history[-(OPENAI_MAX_HISTORY*2):] if OPENAI_MAX_HISTORY > 0 else history
    messages.extend(trimmed)
    messages.append({"role": "user", "content": build_vision_message(caption, image_bytes)})
    loop = asyncio.get_running_loop()
    def _call():
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.6,
            max_tokens=1000,
        )
        return (resp.choices[0].message.content or "").strip()
    return await loop.run_in_executor(None, _call)

async def whisper_transcribe(file_path: str) -> str:
    client = _get_openai_client()
    loop = asyncio.get_running_loop()
    def _call():
        with open(file_path, "rb") as f:
            tr = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        return tr
    return await loop.run_in_executor(None, _call)

async def tts_make_audio(text: str, out_path: str) -> None:
    client = _get_openai_client()
    loop = asyncio.get_running_loop()
    def _call():
        speech = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
            response_format="mp3",
        )
        audio_bytes = speech.read()
        with open(out_path, "wb") as f:
            f.write(audio_bytes)
    await loop.run_in_executor(None, _call)

# --- Rate limit ---
DISABLE_RATE_LIMIT = os.getenv("DISABLE_RATE_LIMIT", "false").lower() == "true"
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

# --- Billing helpers (квоты) ---
async def check_quota(update: Update) -> bool:
    if not SQLA_AVAILABLE:
        return True
    tg_id = update.effective_user.id if update.effective_user else None
    if not tg_id:
        return True
    async with SessionLocal() as session:
        ok, msg = await increment_usage(session, tg_id)
        if not ok:
            await update.effective_chat.send_message(f"{msg}\nКупить доступ: /buy\nТарифы: /pricing")
        return ok

# --- Handlers ---
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    tg_id = update.effective_user.id
    username = update.effective_user.full_name or update.effective_user.username
    # deep link ref
    ref = None
    if context.args:
        payload = " ".join(context.args)
        if payload.startswith("ref") and payload[3:].isdigit():
            ref = int(payload[3:])
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            await upsert_user(session, update.effective_user, referrer=ref)
            await log_message(session, tg_id, update.effective_chat.id, update.message.message_id, "/start")
    await update.message.reply_text(
        "Привет! 👋 Я универсальный ИИ‑бот.\n"
        f"Бесплатно: {PLAN_FREE_QUESTS} запросов. Тарифы: /pricing. Покупка: /buy\n"
        "Реферальная ссылка: /ref\n"
        "Просто пришлите текст/голос/фото/видео."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    await update.message.reply_text(
        "Возможности:\n"
        "• Текст → GPT‑4o (большие ответы с автонарезкой)\n"
        "• Фото → Vision (анализ, идеи)\n"
        "• Голос → Whisper (распознавание и ответ)\n"
        "• Видео → Whisper (расшифровка, конспект)\n"
        "Команды: /start /help /status /stats /pricing /buy /ref /exchange"
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok = bool(OPENAI_API_KEY)
    await update.message.reply_text("✅ Готово" if ok else "⚠️ OPENAI_API_KEY не настроен")

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            users_cnt = await count_users(session)
            msgs_cnt = await count_messages(session)
        await update.message.reply_text(f"Пользователей: {users_cnt}, сообщений: {msgs_cnt}")
    else:
        await update.message.reply_text("Статистика недоступна (in‑memory режим).")

async def cmd_pricing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Тарифы:\n"
        f"• Free — {PLAN_FREE_QUESTS} вопросов\n"
        f"• Starter — ${PLAN_STARTER_PRICE} за {PLAN_STARTER_QUOTA} вопросов\n"
        f"• Pro — ${PLAN_PRO_PRICE} за {PLAN_PRO_QUOTA} вопросов\n"
        f"• Unlimited — ${PLAN_UNLIM_PRICE}/мес (безлимит)\n\n"
        "Купить: /buy"
    )

async def cmd_ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = os.getenv("BOT_USERNAME", "")
    if not bot_username:
        me = await context.bot.get_me()
        bot_username = me.username
    link = f"https://t.me/{bot_username}?start=ref{update.effective_user.id}"
    await update.message.reply_text(f"Ваша реферальная ссылка:\n{link}")

EXCHANGES = [
    {"name": "BestChange", "url": "https://www.bestchange.ru/?p=YOUR_ID"},
    {"name": "Binance P2P", "url": "https://www.binance.com/ru/markets/p2p?ref=YOUR_REF"},
]

async def cmd_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = [f"• {e['name']}: {e['url']} (партнёрская ссылка)" for e in EXCHANGES]
    await update.message.reply_text("Надёжные обменники:\n" + "\n".join(rows))

async def cmd_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton(f"Starter ${PLAN_STARTER_PRICE} (20 вопросов) — PayPal", callback_data="pp:STARTER")],
        [InlineKeyboardButton(f"Pro ${PLAN_PRO_PRICE} (200 вопросов) — PayPal", callback_data="pp:PRO")],
        [InlineKeyboardButton(f"Unlimited ${PLAN_UNLIM_PRICE}/мес — PayPal", callback_data="pp:UNLIM")],
        [InlineKeyboardButton("Оплатить через Telegram Stars (скоро)", callback_data="stars:menu")],
    ]
    await update.message.reply_text("Выберите тариф и способ оплаты:", reply_markup=InlineKeyboardMarkup(kb))

async def on_buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if data.startswith("pp:"):
        plan = data.split(":", 1)[1]
        tg_id = update.effective_user.id
        chat_id = update.effective_chat.id
        if not PUBLIC_BASE_URL:
            await q.edit_message_text("Ошибка конфигурации: нет PUBLIC_BASE_URL")
            return
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(f"{PUBLIC_BASE_URL}/api/paypal/create-order", json={"plan": plan, "tg_id": tg_id, "chat_id": chat_id})
                r.raise_for_status()
                resp = r.json()
            approve = None
            for link in resp.get("links", []):
                if link.get("rel") == "approve":
                    approve = link.get("href")
                    break
            if not approve:
                await q.edit_message_text("Не удалось создать ссылку на оплату PayPal.")
                return
            await q.edit_message_text(f"Оплатите по ссылке:\n{approve}\nПосле оплаты тариф активируется автоматически.")
        except Exception:
            await q.edit_message_text("Ошибка при создании заказа PayPal.")
    elif data == "stars:menu":
        await q.edit_message_text("Поддержка Telegram Stars будет включена позднее.")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not (update.message.text or update.message.caption):
        return
    if rate_limited(update.effective_user.id):
        return
    if not await check_quota(update):
        return

    text = (update.message.text or update.message.caption or "").strip()
    # спец режим “сторис”
    low = text.lower()
    if any(k in low for k in ("сторис", "истор", "story", "stories")):
        text = (
            f"Напиши короткую сторис для соцсетей по запросу: «{text}».\n"
            "Требования: 2–4 экрана, цепляющий первый экран, разговорный тон, уместные эмодзи, финальный призыв к действию. "
            "Без хэштегов. Выводи только текст сторис."
        )

    history: List[Dict[str, Any]] = context.user_data.get("history", [])
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        reply = await llm_chat(text, history)
    except Exception as e:
        logger.exception("LLM error: %s", e)
        reply = "Не удалось сгенерировать ответ. Попробуйте ещё раз."

    # “ответь голосом”
    if "ответь голосом" in low or "голосом ответь" in low:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            outp = tmp.name
        try:
            await tts_make_audio(reply, outp)
            await update.message.reply_audio(audio=open(outp, "rb"), caption="Голосовой ответ")
        finally:
            try:
                os.remove(outp)
            except Exception:
                pass
    else:
        for chunk in chunk_text(reply):
            await update.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    if OPENAI_MAX_HISTORY > 0:
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-(OPENAI_MAX_HISTORY*2):]

async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.photo:
        return
    if rate_limited(update.effective_user.id):
        return
    if not await check_quota(update):
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    bio = io.BytesIO()
    await file.download(out=bio)
    image_bytes = bio.getvalue()
    caption = update.message.caption or ""

    history: List[Dict[str, Any]] = context.user_data.get("history", [])
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        reply = await llm_vision(caption, image_bytes, history)
    except Exception as e:
        logger.exception("Vision error: %s", e)
        reply = "Не удалось обработать изображение."
    for chunk in chunk_text(reply):
        await update.message.reply_text(chunk, disable_web_page_preview=True)

    if OPENAI_MAX_HISTORY > 0:
        history.append({"role": "user", "content": caption})
        history.append({"role": "assistant", "content": reply})
        context.user_data["history"] = history[-(OPENAI_MAX_HISTORY*2):]

async def on_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.voice:
        return
    if rate_limited(update.effective_user.id):
        return
    if not await check_quota(update):
        return
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.RECORD_AUDIO)
        file = await context.bot.get_file(update.message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            p = tmp.name
        try:
            await file.download_to_drive(custom_path=p)
            text = await whisper_transcribe(p)
        finally:
            try:
                os.remove(p)
            except Exception:
                pass
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        reply = await llm_chat(text, context.user_data.get("history", []))
        for chunk in chunk_text(reply):
            await update.message.reply_text(chunk, disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Voice error: %s", e)
        await update.message.reply_text("Не удалось распознать голосовое сообщение.")

async def on_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    video = (msg.video if msg else None) or (msg.video_note if msg else None)
    if not video:
        return
    if rate_limited(update.effective_user.id):
        return
    if not await check_quota(update):
        return
    try:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.UPLOAD_VIDEO)
        file = await context.bot.get_file(video.file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            p = tmp.name
        try:
            await file.download_to_drive(custom_path=p)
            transcript = await whisper_transcribe(p)
        finally:
            try:
                os.remove(p)
            except Exception:
                pass
        prompt = (
            "Дай сжатый пересказ с ключевыми тезисами и практическими рекомендациями по этой расшифровке видео:\n\n"
            f"{transcript}"
        )
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        reply = await llm_chat(prompt, context.user_data.get("history", []))
        for chunk in chunk_text(reply):
            await update.message.reply_text(chunk, disable_web_page_preview=True)
    except Exception as e:
        logger.exception("Video error: %s", e)
        await update.message.reply_text("Не удалось обработать видео.")

async def on_error(update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("PTB error: %s", repr(context.error), exc_info=True)

def build_ptb_application(token: str) -> Application:
    app = ApplicationBuilder().token(token).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("pricing", cmd_pricing))
    app.add_handler(CommandHandler("ref", cmd_ref))
    app.add_handler(CommandHandler("exchange", cmd_exchange))
    app.add_handler(CommandHandler("buy", cmd_buy))
    app.add_handler(CallbackQueryHandler(on_buy_callback))
    app.add_handler(MessageHandler(filters.PHOTO, on_photo))
    app.add_handler(MessageHandler(filters.VOICE, on_voice))
    app.add_handler(MessageHandler(filters.VIDEO | filters.VIDEO_NOTE, on_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)
    return app

# --- Security helpers ---
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
    if cl:
        try:
            if int(cl) > MAX_TELEGRAM_PAYLOAD_BYTES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
        except ValueError:
            pass
    body = await req.body()
    if len(body) > MAX_TELEGRAM_PAYLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
    req._body = body  # starlette private

# --- PayPal API + Webhook ---
paypal_router = APIRouter(prefix="/api/paypal", tags=["paypal"])

def _pp_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

async def paypal_get_token() -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{PAYPAL_BASE}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        )
        r.raise_for_status()
        return r.json()["access_token"]

PLAN_TO_PRICE = {"STARTER": PLAN_STARTER_PRICE, "PRO": PLAN_PRO_PRICE, "UNLIM": PLAN_UNLIM_PRICE}

@paypal_router.post("/create-order")
async def paypal_create_order(req: Request):
    data = await req.json()
    plan = data.get("plan")
    tg_id = int(data.get("tg_id"))
    chat_id = int(data.get("chat_id"))
    if plan not in PLAN_TO_PRICE:
        raise HTTPException(400, "Unknown plan")
    amount = PLAN_TO_PRICE[plan]
    token = await paypal_get_token()
    order = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": f"{plan}-{tg_id}",
            "amount": {"currency_code": "USD", "value": f"{amount}"},
        }],
        "application_context": {"brand_name": "SmartBot", "user_action": "PAY_NOW"},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(f"{PAYPAL_BASE}/v2/checkout/orders", headers=_pp_headers(token), json=order)
        r.raise_for_status()
        resp = r.json()
    if SQLA_AVAILABLE:
        async with SessionLocal() as session:
            p = Payment(tg_id=tg_id, chat_id=chat_id, platform="paypal", plan=plan, amount=amount, status="created", external_id=resp["id"])
            session.add(p)
            await session.commit()
    return resp

@paypal_router.post("/webhook")
async def paypal_webhook(req: Request):
    body_bytes = await req.body()
    headers = req.headers
    token = await paypal_get_token()
    verify_payload = {
        "transmission_id": headers.get("PAYPAL-TRANSMISSION-ID"),
        "transmission_time": headers.get("PAYPAL-TRANSMISSION-TIME"),
        "cert_url": headers.get("PAYPAL-CERT-URL"),
        "auth_algo": headers.get("PAYPAL-AUTH-ALGO"),
        "transmission_sig": headers.get("PAYPAL-TRANSMISSION-SIG"),
        "webhook_id": PAYPAL_WEBHOOK_ID,
        "webhook_event": json.loads(body_bytes.decode("utf-8")),
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        vr = await client.post(f"{PAYPAL_BASE}/v1/notifications/verify-webhook-signature", headers=_pp_headers(token), json=verify_payload)
        vr.raise_for_status()
        v = vr.json()
    if v.get("verification_status") != "SUCCESS":
        raise HTTPException(400, "Invalid PayPal webhook signature")

    event = verify_payload["webhook_event"]
    et = event.get("event_type")
    if et == "CHECKOUT.ORDER.APPROVED":
        order_id = event["resource"]["id"]
        # Capture
        async with httpx.AsyncClient(timeout=20.0) as client:
            cr = await client.post(f"{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture", headers=_pp_headers(token))
            cr.raise_for_status()
            cap = cr.json()
        # plan & tg_id
        ref = cap["purchase_units"][0]["reference_id"]
        plan, tg_id = ref.split("-", 1)
        tg_id = int(tg_id)
        chat_id = None
        if SQLA_AVAILABLE:
            async with SessionLocal() as session:
                from sqlalchemy import select
                pay = (await session.execute(select(Payment).where(Payment.external_id == order_id))).scalar_one_or_none()
                if pay:
                    pay.status = "captured"
                    chat_id = pay.chat_id
                from sqlalchemy import update  # not used but kept if needed
                await activate_plan(session, tg_id, plan)
        try:
            if bot and chat_id:
                await bot.send_message(chat_id, f"Оплата получена. Тариф {plan} активирован ✅")
        except Exception:
            logger.exception("Failed to notify user after PayPal capture")
    return {"ok": True}

# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global application, bot, CURRENT_WEBHOOK_SECRET
    if not TELEGRAM_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN is not set")
    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL/BASE_URL is not set")

    CURRENT_WEBHOOK_SECRET = TELEGRAM_WEBHOOK_SECRET or _generate_secret()

    if SQLA_AVAILABLE:
        try:
            await init_db()
        except Exception:
            logger.exception("DB init failed")

    application = build_ptb_application(TELEGRAM_TOKEN)
    await application.initialize()
    await application.start()
    bot = application.bot

    try:
        commands = [
            BotCommand("start", "Начать"),
            BotCommand("help", "Помощь"),
            BotCommand("status", "Статус"),
            BotCommand("stats", "Статистика"),
            BotCommand("pricing", "Тарифы"),
            BotCommand("buy", "Купить"),
            BotCommand("ref", "Реферальная ссылка"),
            BotCommand("exchange", "Обменники"),
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
        except Exception:
            logger.exception("Failed to delete webhook on shutdown")
        try:
            if application:
                await application.stop()
                await application.shutdown()
        except Exception:
            logger.exception("Failed to shutdown PTB app")
        if SQLA_AVAILABLE and engine:
            try:
                await engine.dispose()
            except Exception:
                logger.exception("Failed to dispose engine")

# --- FastAPI app ---
app = FastAPI(title="Universal Telegram Bot (GPT‑4o)", version="2.0.0", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware, header_name=os.getenv("CORRELATION_ID_HEADER", "X-Request-ID"))
app.add_middleware(GZipMiddleware, minimum_size=512)
_allowed = [h.strip() for h in ALLOWED_HOSTS.split(",")] if ALLOWED_HOSTS else ["*"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed)

# Health
@app.get("/health/live")
async def live(): return {"status": "alive"}

@app.get("/health/ready")
async def ready():
    ok_db = True
    ok_bot = True
    if SQLA_AVAILABLE and engine:
        try:
            from sqlalchemy import text as sa_text
            async with engine.connect() as conn:
                await conn.execute(sa_text("SELECT 1"))
        except Exception:
            ok_db = False
    try:
        me = await bot.get_me() if bot else None
        ok_bot = me is not None
    except Exception:
        ok_bot = False
    code = status.HTTP_200_OK if ok_db and ok_bot else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(content=json.dumps({"db": ok_db, "bot": ok_bot, "status": "ready" if (ok_db and ok_bot) else "not_ready"}), media_type="application/json", status_code=code)

@app.get("/")
async def root():
    return {"message": "Telegram Bot is running (GPT‑4o ready)", "webhook": WEBHOOK_URL}

# Webhook endpoint
@app.post("/telegram")
async def telegram_webhook(request: Request):
    verify_secret_token(request)
    verify_ip_allowlist(request)
    await ensure_payload_size(request)

    if "application/json" not in (request.headers.get("content-type") or ""):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported content-type")
    try:
        body = request._body if hasattr(request, "_body") else await request.body()
        data = json.loads(body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    try:
        upd = Update.de_json(data, bot)
        if upd is None:
            logger.warning("Invalid Update payload")
            return Response(content='{"ok":true}', media_type="application/json", status_code=status.HTTP_200_OK)
        await application.process_update(upd)
        return Response(content='{"ok":true}', media_type="application/json", status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Processing update failed: %s", e)
        return Response(content='{"ok":true}', media_type="application/json", status_code=status.HTTP_200_OK)

# PayPal API routes
app.include_router(paypal_router)
