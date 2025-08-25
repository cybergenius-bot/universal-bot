import os
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
FREE_MESSAGES = int(os.getenv("FREE_MESSAGES", 5))
