import sqlite3
import os

DB_PATH = "agent.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        # Таблица черновиков на согласование
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,          -- post / reply / moderation_review / plan_action
            target TEXT,                 -- канал, чат или ID пользователя
            payload TEXT NOT NULL,       -- текст или варианты через |||
            status TEXT DEFAULT 'pending', -- pending / approved / rejected / expired
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        # Таблица страйков автомодерации
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS strikes (
            user_id TEXT,
            platform TEXT,
            reason TEXT,
            count INTEGER DEFAULT 1,
            last_strike TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, platform)
        )
        ''')
        # Таблица активных диалогов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS dialogs (
            dialog_id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,               -- tg / vk
            user_id TEXT,
            user_name TEXT,
            state TEXT DEFAULT 'active',
            last_message TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()

if __name__ == "__main__":
    init_db()
    print("✅ База данных инициализирована.")
