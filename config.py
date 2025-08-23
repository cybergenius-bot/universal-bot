import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Telegram / OpenAI
    TELEGRAM_TOKEN: str
    OPENAI_API_KEY: str

    # PayPal (по вашим env в Railway)
    PAYPAL_CLIENT_ID: str
    PAYPAL_SECRET: str                       # ⚡️ соответствует Railway
    PAYPAL_MODE: Optional[str] = "sandbox"   # "sandbox" или "live"

    # База данных (Railway создаёт DATABASE_URL)
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"

    # URL / Webhook
    BASE_URL: str = os.getenv("RAILWAY_STATIC_URL", "http://localhost:8000")
    WEBHOOK_URL: Optional[str] = os.getenv("WEBHOOK_URL", None)

    # Порт (Railway задаёт PORT)
    PORT: int = int(os.getenv("PORT", 8000))


settings = Settings()
