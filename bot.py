import os
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8080))
URL = os.getenv("WEBHOOK_URL")  # Например: https://your-app-name.up.railway.app

# Flask приложение
app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TOKEN).build()


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", callback_data="pay")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👋 Добро пожаловать! Нажми кнопку для оплаты:", reply_markup=reply_markup)


# Обработка кнопок
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "pay":
        await query.edit_message_text(
            f"""💳 Перейди по ссылке для оплаты:
https://www.paypal.com/paypalme/youraccount
После оплаты напиши /check"""
        )


# Проверка оплаты
async def check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Оплата проверяется... (тут будет логика)")

# Регистрируем хендлеры
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("check", check))
application.add_handler(CallbackQueryHandler(button))


# Flask webhook endpoint
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
async def webhook() -> str:
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"


# Устанавливаем Webhook при запуске
@app.before_first_request
def setup_webhook():
    asyncio.get_event_loop().create_task(
        application.bot.set_webhook(url=f"{URL}/webhook/{TOKEN}")
    )


# Запуск Flask
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
