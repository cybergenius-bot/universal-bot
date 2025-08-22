import os
import psycopg2
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")

def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            messages_left INT DEFAULT 5,
            plan TEXT DEFAULT 'free',
            expires TIMESTAMP
        );
    ''')
    conn.commit()
    cur.close()
    conn.close()

def get_user(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT messages_left, plan, expires FROM users WHERE user_id=%s;", (user_id,))
    row = cur.fetchone()
    if row is None:
        cur.execute("INSERT INTO users (user_id) VALUES (%s);", (user_id,))
        conn.commit()
        messages_left, plan, expires = 5, 'free', None
    else:
        messages_left, plan, expires = row
    cur.close()
    conn.close()
    return messages_left, plan, expires

def update_user_usage(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE users SET messages_left = messages_left - 1 WHERE user_id = %s;", (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def apply_plan(user_id, plan):
    limits = {"try": (15, 1), "basic": (300, 30), "pro": (99999, 365)}
    messages, days = limits.get(plan, (5, 0))
    expires = datetime.utcnow() + timedelta(days=days)
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("UPDATE users SET messages_left=%s, plan=%s, expires=%s WHERE user_id=%s;",
                (messages, plan, expires, user_id))
    conn.commit()
    cur.close()
    conn.close()

def check_expired(user_id):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT expires FROM users WHERE user_id = %s;", (user_id,))
    row = cur.fetchone()
    if row and row[0] and datetime.utcnow() > row[0]:
        cur.execute("UPDATE users SET plan='free', messages_left=0, expires=NULL WHERE user_id = %s;", (user_id,))
        conn.commit()
    cur.close()
    conn.close()