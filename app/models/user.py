from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from ..database import Base


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    language_code = Column(String(10), default="ru")
    
    # Состояния и настройки
    current_state = Column(String(50), default="idle")
    is_admin = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    
    # Временные метки
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_activity = Column(DateTime, default=func.now())
    
    # Дополнительные данные
    settings = Column(Text, default="{}")  # JSON строка
    
    def __repr__(self):
        return f"<User(id={self.telegram_id}, username={self.username})>"
