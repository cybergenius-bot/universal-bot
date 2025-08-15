import os
from fastapi import FastAPI, Request
from telegram.ext import Application, CommandHandler

# 1. Читаем токен из переменных окружения Railway
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в переменных окружения Railway!")

# 2. Создаем объект бота
bot_app = Application.builder().token(TOKEN).build()

# 3. Создаем FastAPI
app = FastAPI()

# ====== Команды бота ======
async def start(update, context):
    await update.message.reply_text("✅ Бот успешно запущен и готов к работе!")

bot_app.add_handler(CommandHandler("start", start))

# ====== Вебхук ======
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    await bot_app.update_queue.put(data)
    return {"ok": True}

# ====== Старт бота при запуске FastAPI ======
@app.on_event("startup")
async def on_startup():
    await bot_app.initialize()
    await bot_app.start()
    print("🚀 Бот запущен!")

# ====== Остановка бота при завершении ======
@app.on_event("shutdown")
async def on_shutdown():
    await bot_app.stop()
    await bot_app.shutdown()
    print("🛑 Бот остановлен.")
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

# Запуск
if __name__ == "__main__":
    app.run_polling()
