import asyncpg
import asyncio
from datetime import datetime, timedelta
from config import DATABASE_URL, FREE_MESSAGES
from config import settings

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""

async def init_db() -> None:
    """Create required tables if they do not exist."""
    conn = await asyncpg.connect(settings.DATABASE_URL)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            tg_id BIGINT UNIQUE,
            tg_id BIGINT PRIMARY KEY,
            messages_left INT DEFAULT $1,
            expires_at TIMESTAMP,
            current_plan TEXT
            plan TEXT DEFAULT 'free',
            expires TIMESTAMP
        );
    """, FREE_MESSAGES)
    """,
        """,
        settings.FREE_MESSAGES,
    )

    await conn.execute("""
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            tg_id BIGINT,
            amount NUMERIC,
            tariff TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
        """,
    )
    await conn.close()

async def get_user(tg_id):
    conn = await asyncpg.connect(DATABASE_URL)

async def get_user(tg_id: int):
    """Return user info; create user with default limits if missing."""
    conn = await asyncpg.connect(settings.DATABASE_URL)
    user = await conn.fetchrow("SELECT * FROM users WHERE tg_id=$1", tg_id)
    if not user:
        await conn.execute("INSERT INTO users (tg_id, messages_left) VALUES ($1, $2)", tg_id, FREE_MESSAGES)
    row = await conn.fetchrow(
        "SELECT messages_left, plan, expires FROM users WHERE tg_id=$1",
        tg_id,
    )
    if row is None:
        await conn.execute(
            "INSERT INTO users (tg_id, messages_left) VALUES ($1, $2)",
            "INSERT INTO users (tg_id) VALUES ($1)",
            tg_id,
            settings.FREE_MESSAGES,
        )
        user = await conn.fetchrow("SELECT * FROM users WHERE tg_id=$1", tg_id)
        result = (settings.FREE_MESSAGES, "free", None)
    else:
        result = (row["messages_left"], row["plan"], row["expires"])
    await conn.close()
    return user
    return result

async def decrement_messages(tg_id):
    conn = await asyncpg.connect(DATABASE_URL)
    conn = await asyncpg.connect(settings.DATABASE_URL)
    await conn.execute("UPDATE users SET messages_left = messages_left - 1 WHERE tg_id=$1 AND messages_left > 0", tg_id)
    await conn.close()

async def add_messages(tg_id, count):
    conn = await asyncpg.connect(DATABASE_URL)
async def update_user_usage(tg_id: int) -> None:
    """Decrement the remaining message count for the user."""
    conn = await asyncpg.connect(settings.DATABASE_URL)
    await conn.execute("UPDATE users SET messages_left = messages_left + $1 WHERE tg_id=$2", count, tg_id)
    await conn.execute(
        "UPDATE users SET messages_left = messages_left - 1 WHERE tg_id=$1",
        tg_id,
    )
    await conn.close()

async def set_subscription(tg_id, days, plan):
    conn = await asyncpg.connect(DATABASE_URL)

async def apply_plan(tg_id: int, plan: str) -> None:
    """Apply a subscription plan to the user."""
    limits = {"try": (15, 1), "basic": (300, 30), "pro": (99999, 365)}
    messages, days = limits.get(plan, (settings.FREE_MESSAGES, 0))
    expires = datetime.utcnow() + timedelta(days=days)
    conn = await asyncpg.connect(settings.DATABASE_URL)
    new_expiry = datetime.utcnow() + timedelta(days=days)
    await conn.execute("UPDATE users SET expires_at=$1, current_plan=$2 WHERE tg_id=$3", new_expiry, plan, tg_id)
    await conn.execute(
        "UPDATE users SET messages_left=$1, plan=$2, expires=$3 WHERE tg_id=$4",
        messages,
        plan,
        expires,
        tg_id,
    )
    await conn.close()

async def has_active_subscription(tg_id):
    conn = await asyncpg.connect(DATABASE_URL)

async def check_expired(tg_id: int) -> None:
    """Reset plan if the subscription has expired."""
    conn = await asyncpg.connect(settings.DATABASE_URL)
    result = await conn.fetchval("SELECT expires_at FROM users WHERE tg_id=$1", tg_id)
    expires = await conn.fetchval(
        "SELECT expires FROM users WHERE tg_id=$1",
        tg_id,
    )
    if expires and datetime.utcnow() > expires:
        await conn.execute(
            "UPDATE users SET plan='free', messages_left=0, expires=NULL WHERE tg_id=$1",
            tg_id,
        )
    await conn.close()
    if result and result > datetime.utcnow():
        return True
    return False

async def save_payment(tg_id, amount, tariff, status):
    conn = await asyncpg.connect(DATABASE_URL)

async def save_payment(tg_id: int, amount, tariff: str, status: str) -> None:
    """Store payment information."""
    conn = await asyncpg.connect(settings.DATABASE_URL)
    await conn.execute(
        "INSERT INTO payments (tg_id, amount, tariff, status) VALUES ($1, $2, $3, $4)",
        tg_id, amount, tariff, status
        tg_id,
        amount,
        tariff,
        status,
    )
    await conn.close()
