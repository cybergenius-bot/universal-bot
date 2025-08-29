import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения"""
    
    # Telegram настройки
    telegram_token: str
    webhook_url: str
    admin_user_ids: str = ""
    
    # База данных
    database_url: str = "sqlite:///./telegram_bot.db"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Приложение
    debug: bool = False
    secret_key: str
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Логирование
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    @property
    def admin_ids(self) -> List[int]:
        """Получить список ID администраторов"""
        if not self.admin_user_ids:
            return []
        return [int(uid.strip()) for uid in self.admin_user_ids.split(',') if uid.strip()]


# Глобальный объект настроек
settings = Settings()
