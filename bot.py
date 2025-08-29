import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update, Bot
from telegram.ext import Application, MessageHandler, CommandHandler, filters

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получение токена и URL
TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен!")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL не установлен!")

# Создание бота и приложения
bot = Bot(token=TOKEN)
application = Application.builder().token(TOKEN).build()

# Обработчики команд
async def start_command(update: Update, context):
    """Обработчик команды /start"""
    user = update.effective_user
    welcome_text = f"Привет, {user.first_name}! 👋\n\nЯ телеграм бот. Как дела?"
    await update.message.reply_text(welcome_text)
    logger.info(f"Пользователь {user.id} ({user.username}) запустил бота")

async def help_command(update: Update, context):
    """Обработчик команды /help"""
    help_text = """
🤖 Доступные команды:

/start - Запуск бота
/help - Показать эту справку
/status - Статус бота

Просто отправьте сообщение, и я отвечу!
    """
    await update.message.reply_text(help_text)

async def status_command(update: Update, context):
    """Обработчик команды /status"""
    await update.message.reply_text("✅ Бот работает нормально!")

async def handle_message(update: Update, context):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    message_text = update.message.text
    
    logger.info(f"Сообщение от {user.id} ({user.username}): {message_text}")
    
    # Простая логика ответов
    if "привет" in message_text.lower():
        response = f"Привет, {user.first_name}! 😊"
    elif "как дела" in message_text.lower():
        response = "У меня всё отлично! А у тебя как?"
    elif "спасибо" in message_text.lower():
        response = "Пожалуйста! Рад помочь! 😊"
    else:
        response = f"Получил твоё сообщение: '{message_text}'\nОтправь /help для списка команд."
    
    await update.message.reply_text(response)

# Добавление обработчиков
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("status", status_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Современный lifespan manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    try:
        await bot.delete_webhook()
        await bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"✅ Webhook установлен: {WEBHOOK_URL}")
        yield
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске: {e}")
        raise
    finally:
        # Shutdown
        try:
            await bot.delete_webhook()
            logger.info("✅ Webhook удалён при остановке")
        except Exception as e:
            logger.error(f"❌ Ошибка при остановке: {e}")

# Создание FastAPI приложения
app = FastAPI(
    title="Telegram Bot",
    description="Телеграм бот на FastAPI",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """Главная страница"""
    return {"message": "Telegram Bot работает!", "status": "OK"}

@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Обработчик webhook от Telegram"""
    try:
        # Получение данных
        data = await request.json()
        logger.info(f"Webhook получен: {data}")
        
        # Создание Update объекта
        update = Update.de_json(data, bot)
        
        if update:
            # Обработка обновления
            await application.process_update(update)
            return {"ok": True}
        else:
            logger.warning("Получен некорректный update")
            return {"ok": False, "error": "Invalid update"}
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки webhook: {e}", exc_info=True)
        return Response(content="ok", status_code=200)

@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "bot_username": (await bot.get_me()).username if bot else None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:app", host="0.0.0.0", port=8000, reload=True)
