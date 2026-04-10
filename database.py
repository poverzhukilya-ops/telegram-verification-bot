import sqlite3
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            os.makedirs('data', exist_ok=True)
            db_path = 'data/verification.db'
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    status TEXT DEFAULT 'neutral',
                    reputation_score INTEGER DEFAULT 0,
                    verified BOOLEAN DEFAULT 0,
                    verification_date TEXT,
                    last_activity TEXT,
                    notes TEXT
                )
            """)
            
            # Таблица верификаций
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS verifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    verification_date TEXT,
                    video_path TEXT,
                    phrase TEXT,
                    status TEXT,
                    admin_comment TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            # Таблица нарушений
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    violation_date TEXT,
                    violation_type TEXT,
                    description TEXT,
                    severity INTEGER,
                    admin_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            # НОВАЯ ТАБЛИЦА: Таблица рейтинга пользователей
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_ratings (
                    user_id INTEGER PRIMARY KEY,
                    rating INTEGER DEFAULT 0,
                    level TEXT DEFAULT 'Новичок',
                    last_updated TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            # НОВАЯ ТАБЛИЦА: Таблица истории изменений рейтинга
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rating_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    change_date TEXT,
                    change_type TEXT,
                    delta INTEGER,
                    reason TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)
            
            conn.commit()
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Добавление нового пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, last_activity)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, datetime.now().isoformat()))
            
            # Также добавляем запись в таблицу рейтинга
            cursor.execute("""
                INSERT OR IGNORE INTO user_ratings (user_id, rating, level, last_updated)
                VALUES (?, 0, 'Новичок', ?)
            """, (user_id, datetime.now().isoformat()))
            
            conn.commit()
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_user_status(self, user_id: int, status: str, notes: str = None):
        """Обновление статуса пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET status = ?, notes = COALESCE(?, notes), last_activity = ?
                WHERE user_id = ?
            """, (status, notes, datetime.now().isoformat(), user_id))
            conn.commit()
    
    def set_verified(self, user_id: int, verified: bool = True):
        """Отметить пользователя как верифицированного"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users 
                SET verified = ?, verification_date = ?, last_activity = ?
                WHERE user_id = ?
            """, (verified, datetime.now().isoformat(), datetime.now().isoformat(), user_id))
            conn.commit()
    
    def add_verification_record(self, user_id: int, video_path: str, phrase: str, status: str, admin_comment: str = None):
        """Добавление записи о верификации"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO verifications (user_id, verification_date, video_path, phrase, status, admin_comment)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, datetime.now().isoformat(), video_path, phrase, status, admin_comment))
            conn.commit()
    
    def add_violation(self, user_id: int, violation_type: str, description: str, severity: int, admin_id: int):
        """Добавление записи о нарушении"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO violations (user_id, violation_date, violation_type, description, severity, admin_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, datetime.now().isoformat(), violation_type, description, severity, admin_id))
            conn.commit()
    
    def get_pending_verifications(self) -> List[Dict[str, Any]]:
        """Получение списка ожидающих верификации"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users 
                WHERE verified = 0 AND status != 'high_risk'
                ORDER BY last_activity DESC
            """)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_users_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Получение пользователей по статусу"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE status = ?", (status,))
            return [dict(row) for row in cursor.fetchall()]
    
    # ============ НОВЫЕ МЕТОДЫ ДЛЯ РАБОТЫ С РЕЙТИНГОМ ============
    
    def get_user_rating(self, user_id: int) -> int:
        """Получить текущий рейтинг пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT rating FROM user_ratings WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
    
    def update_user_rating(self, user_id: int, delta: int, reason: str = None):
        """Обновить рейтинг пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Обновляем рейтинг
            cursor.execute("""
                UPDATE user_ratings 
                SET rating = rating + ?, last_updated = ?
                WHERE user_id = ?
            """, (delta, datetime.now().isoformat(), user_id))
            
            # Добавляем запись в историю
            cursor.execute("""
                INSERT INTO rating_history (user_id, change_date, change_type, delta, reason)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, datetime.now().isoformat(), 'reaction', delta, reason))
            
            # Получаем новый рейтинг для определения уровня
            cursor.execute("SELECT rating FROM user_ratings WHERE user_id = ?", (user_id,))
            new_rating = cursor.fetchone()[0]
            
            # Обновляем уровень
            level = self._get_level_by_rating(new_rating)
            cursor.execute("""
                UPDATE user_ratings SET level = ? WHERE user_id = ?
            """, (level, user_id))
            
            # Также обновляем reputation_score в таблице users
            cursor.execute("""
                UPDATE users SET reputation_score = ? WHERE user_id = ?
            """, (new_rating, user_id))
            
            conn.commit()
            
            return new_rating
    
    def _get_level_by_rating(self, rating: int) -> str:
        """Определить уровень пользователя по рейтингу"""
        if rating < 0:
            return "Нарушитель"
        elif rating < 100:
            return "Новичок"
        elif rating < 500:
            return "Участник"
        elif rating < 1000:
            return "Активный"
        elif rating < 5000:
            return "Опытный"
        else:
            return "Легенда"
    
    def get_rating_history(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Получить историю изменения рейтинга пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM rating_history 
                WHERE user_id = ? 
                ORDER BY change_date DESC 
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_top_rated_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получить топ пользователей по рейтингу"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT u.user_id, u.username, u.first_name, u.last_name, ur.rating, ur.level
                FROM user_ratings ur
                JOIN users u ON u.user_id = ur.user_id
                ORDER BY ur.rating DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

# Глобальный экземпляр базы данных
db = Database()
