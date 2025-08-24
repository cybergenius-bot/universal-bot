import asyncpg
import asyncio
from datetime import datetime, timedelta
from config import DATABASE_URL, FREE_MESSAGES


async def init_db():
conn = await asyncpg.connect(DATABASE_URL)
await conn.execute("""
CREATE TABLE IF NOT EXISTS users (
id SERIAL PRIMARY KEY,
tg_id BIGINT UNIQUE,
messages_left INT DEFAULT $1,
expires_at TIMESTAMP,
current_plan TEXT
);
""", FREE_MESSAGES)


await conn.execute("""
CREATE TABLE IF NOT EXISTS payments (
id SERIAL PRIMARY KEY,
tg_id BIGINT,
amount NUMERIC,
tariff TEXT,
status TEXT,
created_at TIMESTAMP DEFAULT NOW()
);
""")
await conn.close()


async def get_user(tg_id):
conn = await asyncpg.connect(DATABASE_URL)
user = await conn.fetchrow("SELECT * FROM users WHERE tg_id=$1", tg_id)
if not user:
await conn.execute("INSERT INTO users (tg_id, messages_left) VALUES ($1, $2)", tg_id, FREE_MESSAGES)
user = await conn.fetchrow("SELECT * FROM users WHERE tg_id=$1", tg_id)
await conn.close()
return user


async def decrement_messages(tg_id):
conn = await asyncpg.connect(DATABASE_URL)
await conn.execute("UPDATE users SET messages_left = messages_left - 1 WHERE tg_id=$1 AND messages_left > 0", tg_id)
await conn.close()


async def add_messages(tg_id, count):
conn = await asyncpg.connect(DATABASE_URL)
await conn.execute("UPDATE users SET messages_left = messages_left + $1 WHERE tg_id=$2", count, tg_id)
await conn.close()


async def set_subscription(tg_id, days, plan):
conn = await asyncpg.connect(DATABASE_URL)
new_expiry = datetime.utcnow() + timedelta(days=days)
await conn.execute("UPDATE users SET expires_at=$1, current_plan=$2 WHERE tg_id=$3", new_expiry, plan, tg_id)
await conn.close()


async def has_active_subscription(tg_id):
conn = await asyncpg.connect(DATABASE_URL)
result = await conn.fetchval("SELECT expires_at FROM users WHERE tg_id=$1", tg_id)
await conn.close()
if result and result > datetime.utcnow():
return True
return False


async def save_payment(tg_id, amount, tariff, status):
conn = await asyncpg.connect(DATABASE_URL)
await conn.execute(
"INSERT INTO payments (tg_id, amount, tariff, status) VALUES ($1, $2, $3, $4)",
tg_id, amount, tariff, status
)
await conn.close()
