import os
import httpx

TOKEN = os.getenv("TOKEN")
BASE_URL = os.getenv("RAILWAY_STATIC_URL")  # наш домен
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

@app.on_event("startup")
async def on_startup():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{TOKEN}/setWebhook",
            params={"url": WEBHOOK_URL}
        )
        print("Webhook set result:", resp.json())
async def run_bot():
    await application.start()

@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()
