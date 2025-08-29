import json
from enum import Enum
from typing import Any, Dict, Optional
import redis.asyncio as redis
from ..config import settings


class UserState(Enum):
    """Состояния пользователя"""
    IDLE = "idle"
    WAITING_NAME = "waiting_name"
    WAITING_EMAIL = "waiting_email"
    WAITING_MESSAGE = "waiting_message"
    IN_MENU = "in_menu"
    IN_SUPPORT = "in_support"


class StateService:
    """Сервис для управления состояниями пользователей"""
    
    def __init__(self):
        self.redis = redis.from_url(settings.redis_url)
    
    async def set_state(self, user_id: int, state: UserState, data: Optional[Dict[str, Any]] = None):
        """Установить состояние пользователя"""
        key = f"user_state:{user_id}"
        value = {
            "state": state.value,
            "data": data or {},
            "timestamp": int(time.time())
        }
        await self.redis.set(key, json.dumps(value), ex=3600)  # Expire in 1 hour
    
    async def get_state(self, user_id: int) -> tuple[UserState, Dict[str, Any]]:
        """Получить состояние пользователя"""
        key = f"user_state:{user_id}"
        value = await self.redis.get(key)
        
        if not value:
            return UserState.IDLE, {}
        
        data = json.loads(value)
        state = UserState(data.get("state", "idle"))
        return state, data.get("data", {})
    
    async def clear_state(self, user_id: int):
        """Очистить состояние пользователя"""
        key = f"user_state:{user_id}"
        await self.redis.delete(key)
    
    async def close(self):
        """Закрыть соединение с Redis"""
        await self.redis.close()


# Глобальный объект сервиса состояний
state_service = StateService()
