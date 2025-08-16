import os
import requests
from fastapi import FastAPI, Request
import uvicorn

TOKEN = os.getenv("BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()

def send_message(chat_id, text):
    requests.post(f"{URL}/sendMessage", json={"chat_id": chat_id, "text": text})

@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        # Эхо-ответ
        send_message(chat_id, f"Эхо: {text}")
    return {"ok": True}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))  # Railway сам задаст PORT
    uvicorn.run("main:app", host="0.0.0.0", port=port)
