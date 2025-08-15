import os
import uvicorn
from main import app, application
import asyncio
import logging
import httpx

logging.basicConfig(level=logging.INFO)

PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # например: https://mybot-production.up.railway.app/webhook

async def on_startup():
    # Устанавливаем webhook
    async with httpx.AsyncClient() as client:
        r = await client.post(f"https://api.telegram.org/bot{application.bot.token}/setWebhook", params={"url": WEBHOOK_URL})
        logging.info(f"Webhook установка: {r.json()}")

if __name__ == "__main__":
    asyncio.run(on_startup())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
