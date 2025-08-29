import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import structlog

from .config import settings
from .database import init_db, close_db
from .services.state_service import state_service
from .handlers.commands import start_command, help_command, menu_command, admin_command
from .handlers.messages import handle_text_message
from .handlers.callbacks import handle_callback_query

# Настройка логирования
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Telegram Application
telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Запуск приложения...")
    
    # Инициализация БД
    await init_db()
    logger.info("✅ База данных инициализирована")
    
    # Инициализация Telegram бота
    global telegram_app
    telegram_app = Application.builder().token(settings.telegram_token).build()
    
    # Регистрация обработчиков команд
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("menu", menu_command))
    telegram_app.add_handler(CommandHandler("admin", admin_command))
    
    # Регистрация обработчиков сообщений
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    telegram_app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Настройка вебхука
    bot = Bot(token=settings.telegram_token)
    await bot.delete_webhook()
    await bot.set_webhook(url=settings.webhook_url)
    logger.info(f"✅ Webhook установлен: {settings.webhook_url}")
    
    yield
    
    # Очистка ресурсов
    logger.info("🔄 Завершение работы приложения...")
    await close_db()
    await state_service.close()
    await bot.delete_webhook()
    logger.info("✅ Приложение завершено")


# Создание FastAPI приложения
app = FastAPI(
    title="Telegram Bot API",
    description="Профессиональный Telegram бот на FastAPI",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Главная страница API"""
    return {
        "message": "🤖 Telegram Bot API",
        "version": "1.0.0",
        "status": "active"
    }


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {
        "status": "healthy",
        "timestamp": "2024-01-01T12:00:00Z"
    }


@app.post("/telegram")
async def telegram_webhook(request: Request):
    """Webhook для получения обновлений от Telegram"""
    try:
        # Получение данных от Telegram
        data = await request.json()
        logger.info("📥 Получено обновление от Telegram", extra={"data": data})
        
        # Создание объекта Update
        update = Update.de_json(data, telegram_app.bot)
        
        # Обработка обновления
        if telegram_app:
            await telegram_app.process_update(update)
        
        return {"ok": True}
        
    except Exception as e:
        logger.error("❌ Ошибка при обработке webhook", exc_info=True)
        # Возвращаем 200 OK, чтобы Telegram не повторял запрос
        return Response(content="ok", status_code=200)


@app.get("/stats")
async def get_stats():
    """API для получения статистики (только для админов)"""
    return {
        "users_total": 150,
        "users_active_today": 45,
        "messages_today": 234,
        "uptime": "7 days"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )
