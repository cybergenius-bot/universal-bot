from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..database import Base


class Message(Base):
    """Модель сообщения"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    telegram_message_id = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    
    # Содержимое сообщения
    text = Column(Text, nullable=True)
    message_type = Column(String(20), default="text")  # text, photo, document, etc.
    
    # Метаданные
    created_at = Column(DateTime, default=func.now())
    chat_id = Column(Integer, nullable=False)
    
    # Связи
    user = relationship("User", backref="messages")
    
    def __repr__(self):
        return f"<Message(id={self.id}, user_id={self.user_id})>"
