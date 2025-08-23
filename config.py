import os
from pydantic import BaseSettings


class Settings(BaseSettings):
    TELEGRAM_TOKEN: str
    OPENAI_API_KEY: str
    PAYPAL_CLIENT_ID: str
    PAYPAL_CLIENT_SECRET: str
    PAYPAL_WEBHOOK_ID: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./bot.db"
    BASE_URL: str = "http://localhost:8000"
    PORT: int = int(os.getenv("PORT", 8000))


settings = Settings()
