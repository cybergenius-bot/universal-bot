from fastapi import FastAPI, Request
import requests
import os

TOKEN = os.environ.get("BOT_TOKEN", "ТВОЙ_ТОКЕН")  # токен из Railway → Variables
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = FastAPI()


# простой echo-хендлер
@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != TOKEN:  # защита от чужих запросов
        return {"ok": False, "description": "invalid token"}

    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        # отправляем обратно то, что написал пользователь
        requests.post(f"{TELEGRAM_API}/sendMessage", json={
            "chat_id": chat_id,
            "text": f"Эхо: {text}"
        })

    return {"ok": True}


# запуск локально или на Railway
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Railway даёт свой порт
    uvicorn.run("main:app", host="0.0.0.0", port=port)
