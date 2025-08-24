import os

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"

PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")

FREE_MESSAGES = 5

TARIFFS = {
    "start": {"price": 10, "messages": 20, "expires_days": None},
    "standard": {"price": 30, "messages": 200, "expires_days": None},
    "premium": {"price": 50, "messages": None, "expires_days": 30},
}
