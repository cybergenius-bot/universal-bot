from fastapi import FastAPI, Request
import requests
import os

TOKEN = os.getenv("BOT_TOKEN")
URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

app = FastAPI()

@app.post("/")
async def webhook(request: Request):
    data = await request.json()
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        
        # Логика ответов (вместо эхо)
        if text.lower() in ["привет", "hello", "shalom"]:
            reply = "Привет 👋! Чем помочь?"
        elif "доллар" in text.lower():
            reply = "💵 Хочешь обменять доллары? Вот проверенные обменники:\n👉 BestChange\n👉 Binance"
        else:
            reply = "Я пока учусь 😉 Спроси меня про обмен валют или напиши 'привет'."
        
        requests.post(URL, json={"chat_id": chat_id, "text": reply})
    return {"ok": True}
