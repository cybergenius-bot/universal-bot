"""Application configuration using Pydantic settings."""

from __future__ import annotations

import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_MODEL = "gpt-4o"
FREE_MESSAGES = 20
"""Application configuration using Pydantic settings."""

from __future__ import annotations

try:  # Pydantic v2
    from pydantic_settings import BaseSettings
except Exception:  # pragma: no cover - fallback for Pydantic v1
    from pydantic import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    TELEGRAM_TOKEN: str | None = None
    WEBHOOK_URL: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o"
    FREE_MESSAGES: int = 20
    DATABASE_URL: str | None = None

    PAYPAL_CLIENT_ID: str | None = None
    PAYPAL_SECRET: str | None = None
    PAYPAL_MODE: str = "sandbox"
    BASE_URL: str | None = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Export individual settings for backward compatibility
TELEGRAM_TOKEN = settings.TELEGRAM_TOKEN
WEBHOOK_URL = settings.WEBHOOK_URL
OPENAI_API_KEY = settings.OPENAI_API_KEY
DATABASE_URL = settings.DATABASE_URL
OPENAI_MODEL = settings.OPENAI_MODEL
FREE_MESSAGES = settings.FREE_MESSAGES
