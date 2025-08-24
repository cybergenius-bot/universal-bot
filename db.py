from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float
import datetime
from config import settings

# Приводим DATABASE_URL к asyncpg-формату
db_url = settings.DATABASE_URL
if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Создание асинхронного движка
engine = create_async_engine(db_url, echo=False, future=True)

# Создание сессии
SessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Базовый класс моделей
Base = declarative_base()

# Модель пользователя
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(Integer, unique=True, index=True)
    lang = Column(String, default="ru")
    free_left = Column(Integer, default=5)
    paid_left = Column(Integer, default=0)
    is_unlimited = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Модель платежа
class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    tg_id = Column(Integer, index=True)
    amount = Column(Float)
    plan = Column(String)
    status = Column(String)
    provider_payment_id = Column(String, unique=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

# Инициализация базы данных
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
