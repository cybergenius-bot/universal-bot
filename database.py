# database.py
import os
import psycopg2

# Получаем URL из переменных окружения
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Переменная окружения DATABASE_URL не задана")

# Подключаемся к внешней базе по URL
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

def ensure_table():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_limits (
        user_id BIGINT PRIMARY KEY,
        usage_count INTEGER DEFAULT 0
    )
    """)
    conn.commit()

# При импорте сразу гарантируем создание таблицы
ensure_table()
