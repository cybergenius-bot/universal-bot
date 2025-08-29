from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.user import User
from ..database import get_db
import json


class UserService:
    """Сервис для работы с пользователями"""
    
    @staticmethod
    async def get_or_create_user(telegram_id: int, **kwargs) -> User:
        """Получить или создать пользователя"""
        async with get_db() as session:
            # Попытаться найти существующего пользователя
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                # Обновить информацию о пользователе
                for key, value in kwargs.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                user.last_activity = func.now()
            else:
                # Создать нового пользователя
                user = User(telegram_id=telegram_id, **kwargs)
                session.add(user)
            
            await session.commit()
            return user
    
    @staticmethod
    async def update_user(telegram_id: int, **kwargs) -> Optional[User]:
        """Обновить данные пользователя"""
        async with get_db() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            
            if user:
                for key, value in kwargs.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
                user.updated_at = func.now()
                await session.commit()
            
            return user
    
    @staticmethod
    async def get_user_settings(telegram_id: int) -> dict:
        """Получить настройки пользователя"""
        async with get_db() as session:
            result = await session.execute(
                select(User.settings).where(User.telegram_id == telegram_id)
            )
            settings_json = result.scalar_one_or_none()
            
            if settings_json:
                return json.loads(settings_json)
            return {}
    
    @staticmethod
    async def update_user_settings(telegram_id: int, settings: dict):
        """Обновить настройки пользователя"""
        async with get_db() as session:
            await session.execute(
                update(User)
                .where(User.telegram_id == telegram_id)
                .values(settings=json.dumps(settings))
            )
            await session.commit()
    
    @staticmethod
    async def is_admin(telegram_id: int) -> bool:
        """Проверить, является ли пользователь админом"""
        from ..config import settings
        return telegram_id in settings.admin_ids
