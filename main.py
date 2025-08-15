import os
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в переменных окружения Railway!")

app = FastAPI()
application = ApplicationBuilder().token(TOKEN).build()

# Команда /start
async def start(update: Update, context):
    await update.message.reply_text("Привет! Бот работает ✅")

# Ответ на любое сообщение
async def echo(update: Update, context):
    await update.message.reply_text(f"Вы написали: {update.message.text}")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Обработка вебхука
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}

# Проверка
@app.get("/")
def home():
    return {"status": "Бот запущен ✅"}
3. Файл run.py
python
Копировать
Редактировать
import os
import uvicorn
from main import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

