# database.py
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_path="verification.db"):
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
            
            conn.commit()
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """Добавление нового пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, last_activity)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, datetime.now().isoformat()))
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

# Глобальный экземпляр базы данных
db = Database()