import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..services.user_service import UserService
from ..services.state_service import state_service, UserState
from ..utils.keyboards import Keyboards

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Создаем или обновляем пользователя
    await UserService.get_or_create_user(
        telegram_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code
    )
    
    # Сбрасываем состояние
    await state_service.set_state(user.id, UserState.IDLE)
    
    welcome_message = f"""
🎉 Добро пожаловать, {user.first_name}!

Я многофункциональный бот, который поможет вам:
• 📊 Получать статистику
• ⚙️ Настраивать параметры
• 💬 Общаться с поддержкой

Используйте меню ниже для навигации.
    """
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=Keyboards.main_menu()
    )
    
    logger.info(f"User {user.id} started the bot")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📖 **Справка по боту**

**Основные команды:**
• /start - Запустить бота
• /help - Показать эту справку
• /menu - Открыть главное меню
• /settings - Настройки
• /support - Связаться с поддержкой

**Как пользоваться:**
1. Используйте команды или кнопки меню
2. Следуйте инструкциям бота
3. В любой момент можете вернуться в главное меню командой /menu

**Нужна помощь?**
Обратитесь в поддержку через /support
    """
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=Keyboards.main_menu()
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /menu"""
    user = update.effective_user
    await state_service.set_state(user.id, UserState.IN_MENU)
    
    await update.message.reply_text(
        "📋 Главное меню:",
        reply_markup=Keyboards.main_menu()
    )


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /admin (только для админов)"""
    user = update.effective_user
    
    if not await UserService.is_admin(user.id):
        await update.message.reply_text("❌ У вас нет прав доступа к этой команде.")
        return
    
    await update.message.reply_text(
        "🔧 Панель администратора:",
        reply_markup=Keyboards.admin_menu()
    )
    
    logger.info(f"Admin {user.id} accessed admin panel")
