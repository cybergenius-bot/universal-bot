import os
from fastapi import FastAPI, Request
import httpx

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = f"/webhook/{TOKEN}"
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()


@app.get("/")
async def root():
    return {"status": "ok"}


@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" in data and "text" in data["message"]:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"]

        # Отвечаем тем же текстом (эхо)
        async with httpx.AsyncClient() as client:
            await client.post(f"{TELEGRAM_API_URL}/sendMessage", json={
                "chat_id": chat_id,
                "text": text
            })

    return {"ok": True}

# запуск локально или на Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Railway даёт свой порт
    uvicorn.run("main:app", host="0.0.0.0", port=port)
