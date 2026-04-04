# rating_db.py
import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class RatingDB:
    def __init__(self, db_path='rating.db'):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных рейтинга"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    join_date TIMESTAMP,
                    last_active TIMESTAMP,
                    verified BOOLEAN DEFAULT 0,
                    status TEXT DEFAULT 'active'
                )
            ''')
            
            # Таблица рейтинга
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rating (
                    user_id INTEGER PRIMARY KEY,
                    points INTEGER DEFAULT 100,
                    level INTEGER DEFAULT 1,
                    projects_participated INTEGER DEFAULT 0,
                    projects_created INTEGER DEFAULT 0,
                    total_investments REAL DEFAULT 0,
                    total_profit REAL DEFAULT 0,
                    reputation REAL DEFAULT 0,
                    last_updated TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица действий пользователя
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action_type TEXT,
                    points_change INTEGER,
                    description TEXT,
                    created_at TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            conn.commit()
            logger.info("База данных рейтинга инициализирована")
    
    def add_or_update_user(self, user_id, username, first_name, last_name):
        """Добавление или обновление пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name, last_active, join_date)
                VALUES (?, ?, ?, ?, ?, COALESCE((SELECT join_date FROM users WHERE user_id = ?), ?))
            ''', (user_id, username, first_name, last_name, datetime.now(), user_id, datetime.now()))
            
            # Проверяем, есть ли пользователь в таблице рейтинга
            cursor.execute('SELECT user_id FROM rating WHERE user_id = ?', (user_id,))
            if not cursor.fetchone():
                cursor.execute('''
                    INSERT INTO rating (user_id, points, level, last_updated)
                    VALUES (?, 100, 1, ?)
                ''', (user_id, datetime.now()))
            
            conn.commit()
    
    def update_rating(self, user_id, action_type, points_change, description=""):
        """Обновление рейтинга пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Обновляем очки
            cursor.execute('''
                UPDATE rating 
                SET points = points + ?, last_updated = ?
                WHERE user_id = ?
            ''', (points_change, datetime.now(), user_id))
            
            # Обновляем уровень (каждые 100 очков = новый уровень)
            cursor.execute('''
                UPDATE rating 
                SET level = (points / 100) + 1
                WHERE user_id = ?
            ''', (user_id,))
            
            # Записываем действие
            cursor.execute('''
                INSERT INTO user_actions (user_id, action_type, points_change, description, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, action_type, points_change, description, datetime.now()))
            
            conn.commit()
    
    def add_project_participation(self, user_id, is_creator=False, investment=0):
        """Участие в проекте"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if is_creator:
                cursor.execute('''
                    UPDATE rating 
                    SET projects_created = projects_created + 1,
                        points = points + 50
                    WHERE user_id = ?
                ''', (user_id,))
                self.update_rating(user_id, 'create_project', 50, f"Создал проект")
            else:
                cursor.execute('''
                    UPDATE rating 
                    SET projects_participated = projects_participated + 1,
                        points = points + 20
                    WHERE user_id = ?
                ''', (user_id,))
                self.update_rating(user_id, 'participate_project', 20, f"Участвовал в проекте")
            
            if investment > 0:
                cursor.execute('''
                    UPDATE rating 
                    SET total_investments = total_investments + ?
                    WHERE user_id = ?
                ''', (investment, user_id))
                self.update_rating(user_id, 'investment', int(investment/1000), f"Инвестировал {investment} руб.")
            
            conn.commit()
    
    def get_rating_list(self, limit=50):
        """Получение списка рейтинга"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.user_id,
                    u.username,
                    u.first_name,
                    u.last_name,
                    r.points,
                    r.level,
                    r.projects_participated,
                    r.projects_created,
                    r.total_investments,
                    r.total_profit,
                    r.reputation
                FROM users u
                JOIN rating r ON u.user_id = r.user_id
                WHERE u.status = 'active'
                ORDER BY r.points DESC, r.reputation DESC
                LIMIT ?
            ''', (limit,))
            
            return cursor.fetchall()
    
    def get_user_rating(self, user_id):
        """Получение рейтинга конкретного пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    u.username,
                    u.first_name,
                    u.last_name,
                    r.points,
                    r.level,
                    r.projects_participated,
                    r.projects_created,
                    r.total_investments,
                    r.reputation
                FROM users u
                JOIN rating r ON u.user_id = r.user_id
                WHERE u.user_id = ?
            ''', (user_id,))
            
            return cursor.fetchone()
    
    def get_stats(self):
        """Получение общей статистики"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_users,
                    SUM(points) as total_points,
                    SUM(projects_participated + projects_created) as total_projects
                FROM users u
                JOIN rating r ON u.user_id = r.user_id
                WHERE u.status = 'active'
            ''')
            result = cursor.fetchone()
            
            total_users = result[0] or 0
            total_points = result[1] or 0
            total_projects = result[2] or 0
            avg_points = total_points // total_users if total_users > 0 else 0
            
            return {
                'total_users': total_users,
                'total_points': total_points,
                'total_projects': total_projects,
                'avg_points': avg_points
            }

rating_db = RatingDB()