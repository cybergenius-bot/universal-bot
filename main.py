from telegram.ext import Application, CommandHandler

# 🔹 Вставь сюда токен, который дал BotFather (без пробелов, без кавычек вокруг)
TOKEN = "ТВОЙ_ТОКЕН"

# Команда /start
async def start(update, context):
    await update.message.reply_text("Привет! ✅ Бот запущен и работает в polling-режиме.")

# Главная функция
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()

if __name__ == "__main__":
    main()
