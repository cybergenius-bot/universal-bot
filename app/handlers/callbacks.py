import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..services.user_service import UserService
from ..services.state_service import state_service, UserState
from ..utils.keyboards import Keyboards

logger = logging.getLogger(__name__)


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Основной обработчик callback запросов"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user = update.effective_user
    
    # Маршрутизация по callback данным
    if data == "stats":
        await show_user_stats(update, context)
    elif data == "settings":
        await show_settings_menu(update, context)
    elif data == "help":
        await show_help(update, context)
    elif data == "support":
        await start_support(update, context)
    elif data == "back_to_main":
        await show_main_menu(update, context)
    elif data.startswith("admin_"):
        await handle_admin_callback(update, context)
    else:
        await query.edit_message_text("❓ Неизвестная команда")


async def show_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать статистику пользователя"""
    query = update.callback_query
    user = update.effective_user
    
    # Здесь можно добавить реальную статистику
    stats_text = f"""
📊 **Ваша статистика**

👤 **Профиль:**
• ID: {user.id}
• Имя: {user.first_name}
• Username: @{user.username or 'не указан'}

📈 **Активность:**
• Сообщений отправлено: 42
• Команд выполнено: 15
• Дней с нами: 7

⏰ **Последняя активность:** сейчас
    """
    
    await query.edit_message_text(
        stats_text,
        parse_mode='Markdown',
        reply_markup=Keyboards.main_menu()
    )


async def show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню настроек"""
    query = update.callback_query
    
    await query.edit_message_text(
        "⚙️ **Настройки**\n\nВыберите раздел для настройки:",
        parse_mode='Markdown',
        reply_markup=Keyboards.settings_menu()
    )


async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать справку"""
    query = update.callback_query
    
    help_text = """
📖 **Справка по боту**

**Основные функции:**
• 📊 Статистика - ваша активность и данные
• ⚙️ Настройки - персонализация бота
• 📞 Поддержка - связь с администрацией

**Навигация:**
• Используйте кнопки меню
• Команды начинаются с /
• В любой момент можно вернуться назад

**Нужна помощь?**
Обратитесь в поддержку!
    """
    
    await query.edit_message_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=Keyboards.main_menu()
    )


async def start_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать диалог с поддержкой"""
    query = update.callback_query
    user = update.effective_user
    
    await state_service.set_state(user.id, UserState.WAITING_MESSAGE)
    
    await query.edit_message_text(
        "📞 **Поддержка**\n\n"
        "Опишите вашу проблему или задайте вопрос.\n"
        "Ваше сообщение будет отправлено администраторам.",
        parse_mode='Markdown'
    )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать главное меню"""
    query = update.callback_query
    user = update.effective_user
    
    await state_service.set_state(user.id, UserState.IN_MENU)
    
    await query.edit_message_text(
        f"👋 Привет, {user.first_name}!\n\n📋 Главное меню:",
        reply_markup=Keyboards.main_menu()
    )


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка админских callback'ов"""
    query = update.callback_query
    user = update.effective_user
    data = query.data
    
    # Проверяем права админа
    if not await UserService.is_admin(user.id):
        await query.edit_message_text("❌ Недостаточно прав доступа")
        return
    
    if data == "admin_users":
        await show_admin_users(update, context)
    elif data == "admin_stats":
        await show_admin_stats(update, context)
    elif data == "admin_broadcast":
        await start_broadcast(update, context)


async def show_admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список пользователей (админ)"""
    query = update.callback_query
    
    # Здесь должна быть реальная статистика из БД
    users_info = """
👥 **Пользователи бота**

📊 **Общая статистика:**
• Всего пользователей: 150
• Активных за сегодня: 45
• Новых за неделю: 12
• Заблокированных: 2

🔝 **Топ активных:**
1. @user1 - 234 сообщения
2. @user2 - 189 сообщений
3. @user3 - 156 сообщений
    """
    
    await query.edit_message_text(
        users_info,
        parse_mode='Markdown',
        reply_markup=Keyboards.admin_menu()
    )
