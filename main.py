import os
from fastapi import FastAPI, Request

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print("Update from Telegram:", data)
    return {"ok": True}
            send_message(chat_id, f"Вы написали: {text}")

    return {"ok": True}

def send_message(chat_id, text):
    requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text})
