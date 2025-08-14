import os
from fastapi import FastAPI, Request, BackgroundTasks
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === Конфигурация ===
TOKEN = os.getenv("TELEGRAM_TOKEN")  # токен бота
RAILWAY_URL = "universal-bot-production.up.railway.app"  # твой Railway-домен
WEBHOOK_PATH = "/webhook"

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

# === Команды бота ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Универсальный бот запущен и готов к работе!")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Доступные команды: /start, /help")

bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("help", help_cmd))

# === Проверка сервера ===
@app.get("/")
async def root():
    return {"status": "ok"}

# === Устанавливаем вебхук при старте ===
@app.on_event("startup")
async def on_startup():
    webhook_url = f"https://{RAILWAY_URL}{WEBHOOK_PATH}"
    await bot_app.bot.set_webhook(webhook_url)
    print(f"📌 Webhook установлен: {webhook_url}")

# === Обрабатываем входящие обновления ===
@app.post(WEBHOOK_PATH)
async def process_webhook(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    # Обрабатываем в фоне → Telegram всегда получает быстрый ответ
    background_tasks.add_task(bot_app.process_update, update)
    return {"ok": True}
