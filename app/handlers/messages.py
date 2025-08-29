import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..services.user_service import UserService
from ..services.state_service import state_service, UserState
from ..models.message import Message
from ..database import get_db

logger = logging.getLogger(__name__)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user = update.effective_user
    message = update.message
    
    # Получаем состояние пользователя
    current_state, state_data = await state_service.get_state(user.id)
    
    # Сохраняем сообщение в БД
    await save_message(message)
    
    # Обрабатываем сообщение в зависимости от состояния
    if current_state == UserState.WAITING_NAME:
        await handle_name_input(update, context)
    elif current_state == UserState.WAITING_EMAIL:
        await handle_email_input(update, context)
    elif current_state == UserState.WAITING_MESSAGE:
        await handle_support_message(update, context)
    else:
        await handle_default_message(update, context)


async def handle_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода имени"""
    user = update.effective_user
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("❌ Имя слишком короткое. Попробуйте еще раз:")
        return
    
    # Сохраняем имя в настройках пользователя
    settings = await UserService.get_user_settings(user.id)
    settings['display_name'] = name
    await UserService.update_user_settings(user.id, settings)
    
    # Переводим в следующее состояние
    await state_service.set_state(user.id, UserState.WAITING_EMAIL)
    
    await update.message.reply_text(
        f"✅ Отлично! Имя '{name}' сохранено.\n"
        "Теперь введите ваш email:"
    )


async def handle_email_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода email"""
    user = update.effective_user
    email = update.message.text.strip()
    
    # Простая валидация email
    if '@' not in email or '.' not in email:
        await update.message.reply_text("❌ Неверный формат email. Попробуйте еще раз:")
        return
    
    # Сохраняем email
    settings = await UserService.get_user_settings(user.id)
    settings['email'] = email
    await UserService.update_user_settings(user.id, settings)
    
    # Завершаем процесс регистрации
    await state_service.set_state(user.id, UserState.IDLE)
    
    await update.message.reply_text(
        f"✅ Email '{email}' сохранен!\n"
        "Регистрация завершена. Добро пожаловать!"
    )


async def handle_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка сообщения в поддержку"""
    user = update.effective_user
    message_text = update.message.text
    
    # Отправляем сообщение админам
    from ..config import settings
    for admin_id in settings.admin_ids:
        try:
            await context.bot.send_message(
                admin_id,
                f"📩 **Новое сообщение в поддержку**\n"
                f"От: {user.first_name} (@{user.username})\n"
                f"ID: {user.id}\n\n"
                f"Сообщение:\n{message_text}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send message to admin {admin_id}: {e}")
    
    # Сбрасываем состояние
    await state_service.set_state(user.id, UserState.IDLE)
    
    await update.message.reply_text(
        "✅ Ваше сообщение отправлено в поддержку!\n"
        "Мы ответим вам в ближайшее время."
    )


async def handle_default_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычных сообщений"""
    await update.message.reply_text(
        "🤔 Я вас не понимаю. Используйте команды или кнопки меню.\n"
        "Для получения помощи наберите /help"
    )


async def save_message(message):
    """Сохранение сообщения в БД"""
    try:
        async with get_db() as session:
            msg = Message(
                telegram_message_id=message.message_id,
                user_id=message.from_user.id,
                text=message.text,
                message_type="text",
                chat_id=message.chat_id
            )
            session.add(msg)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to save message: {e}")
