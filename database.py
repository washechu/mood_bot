import sqlite3
import os
from datetime import datetime, timedelta, timezone

MOSCOW_TZ = timezone(timedelta(hours=3))

DB_PATH = os.environ.get('DB_PATH', 'mood_tracker.db')

CATEGORIES = ['Здоровье', 'Настроение', 'Активность', 'Еда', 'Сон', 'Саморазвитие']


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            first_name  TEXT,
            reminder_time TEXT DEFAULT '21:00',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            date        DATE,
            category    TEXT,
            score       INTEGER,
            comment     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date, category),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    conn.commit()
    conn.close()


def add_or_update_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)',
        (user_id, username, first_name)
    )
    conn.commit()
    conn.close()


def set_reminder_time(user_id: int, time_str: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET reminder_time = ? WHERE user_id = ?', (time_str, user_id))
    conn.commit()
    conn.close()


def get_reminder_time(user_id: int) -> str:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT reminder_time FROM users WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else '21:00'


def get_all_users():
    """Returns list of (user_id, reminder_time)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT user_id, reminder_time FROM users')
    users = c.fetchall()
    conn.close()
    return users


def save_entry(user_id: int, date: str, category: str, score: int, comment: str | None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT OR REPLACE INTO entries (user_id, date, category, score, comment)
           VALUES (?, ?, ?, ?, ?)''',
        (user_id, date, category, score, comment)
    )
    conn.commit()
    conn.close()


def get_days_since_first_entry(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT MIN(date) FROM entries WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    conn.close()
    if not row or not row[0]:
        return 0
    first = datetime.strptime(row[0], '%Y-%m-%d').date()
    return (datetime.now(MOSCOW_TZ).date() - first).days


def get_entries(user_id: int, days: int = 30):
    """Returns list of (date, category, score, comment)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''SELECT date, category, score, comment FROM entries
           WHERE user_id = ? AND date >= date('now', ?)
           ORDER BY date ASC''',
        (user_id, f'-{days} days')
    )
    rows = c.fetchall()
    conn.close()
    return rows


def has_entry_today(user_id: int) -> bool:
    today = datetime.now(MOSCOW_TZ).strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT COUNT(*) FROM entries WHERE user_id = ? AND date = ?',
        (user_id, today)
    )
    count = c.fetchone()[0]
    conn.close()
    return count >= len(CATEGORIES)
