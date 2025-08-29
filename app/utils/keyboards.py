from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


class Keyboards:
    """Класс для создания клавиатур"""
    
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        """Главное меню"""
        keyboard = [
            [
                InlineKeyboardButton("📊 Статистика", callback_data="stats"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="settings")
            ],
            [
                InlineKeyboardButton("❓ Помощь", callback_data="help"),
                InlineKeyboardButton("📞 Поддержка", callback_data="support")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def settings_menu() -> InlineKeyboardMarkup:
        """Меню настроек"""
        keyboard = [
            [
                InlineKeyboardButton("🌍 Язык", callback_data="settings_language"),
                InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def admin_menu() -> InlineKeyboardMarkup:
        """Админ меню"""
        keyboard = [
            [
                InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
                InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
            ],
            [
                InlineKeyboardButton("📤 Рассылка", callback_data="admin_broadcast"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def confirm_action(action: str) -> InlineKeyboardMarkup:
        """Подтверждение действия"""
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data=f"confirm_{action}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"cancel_{action}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def contact_keyboard() -> ReplyKeyboardMarkup:
        """Клавиатура для отправки контакта"""
        keyboard = [
            [KeyboardButton("📱 Поделиться контактом", request_contact=True)]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
