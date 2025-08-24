import os
from dotenv import load_dotenv
load_dotenv()


TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


TARIFFS = {
"buy_start": {"messages": 20, "price": 10},
"buy_standard": {"messages": 200, "price": 30},
"buy_premium": {"messages": float("inf"), "price": 50}
}
