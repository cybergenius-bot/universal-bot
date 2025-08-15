import os
from telegram.ext import Application, CommandHandler

# Читаем токен из Railway переменной
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("❌ Не найден TOKEN в переменных окружения Railway!")

# Команда /start
async def start(update, context):
    await update.message.reply_text("✅ Бот запущен и готов к работе!")

# Создаём приложение
app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

# Запуск
if __name__ == "__main__":
    app.run_polling()
