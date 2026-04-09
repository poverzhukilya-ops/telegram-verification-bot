import sqlite3
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class RatingDB:
    def add_or_update_user_preserve_points(self, user_id, username, first_name, last_name):
    """Добавление или обновление пользователя БЕЗ сброса очков"""
    with sqlite3.connect(self.db_path) as conn:
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь в таблице users
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        user_exists = cursor.fetchone()
        
        if user_exists:
            # Обновляем только информацию о пользователе
            cursor.execute('''
                UPDATE users 
                SET username = ?, first_name = ?, last_name = ?, last_active = ?
                WHERE user_id = ?
            ''', (username, first_name, last_name, datetime.now(), user_id))
            
            # Проверяем, есть ли запись в rating
            cursor.execute('SELECT user_id FROM rating WHERE user_id = ?', (user_id,))
            rating_exists = cursor.fetchone()
            
            if not rating_exists:
                # Создаем запись в rating с 0 очками
                cursor.execute('''
                    INSERT INTO rating (user_id, points, level, last_updated)
                    VALUES (?, 0, 1, ?)
                ''', (user_id, datetime.now()))
            
            conn.commit()
            return 'updated'
        else:
            # Создаем нового пользователя
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name, join_date, last_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, datetime.now(), datetime.now()))
            
            # Создаем запись в rating с 0 очками
            cursor.execute('''
                INSERT INTO rating (user_id, points, level, last_updated)
                VALUES (?, 0, 1, ?)
            ''', (user_id, datetime.now()))
            
            conn.commit()
            return 'added'
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
                    points INTEGER DEFAULT 0,
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
            
            # Таблица реакций на сообщения
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_reactions (
                    message_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    author_id INTEGER NOT NULL,
                    reaction INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (message_id, user_id)
                )
            ''')
            
            # Индексы
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_message_author 
                ON message_reactions(message_id, author_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_user_reactions 
                ON message_reactions(user_id)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_author_reactions 
                ON message_reactions(author_id)
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
                    VALUES (?, 0, 1, ?)
                ''', (user_id, datetime.now()))
            else:
                # Если есть, обновляем только last_updated, но не меняем points
                cursor.execute('''
                    UPDATE rating SET last_updated = ? WHERE user_id = ?
                ''', (datetime.now(), user_id))
            
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
                ORDER BY r.points DESC, r.reputation DESC
                LIMIT ?
            ''', (limit,))
            
            return cursor.fetchall()
    
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
    
    # ============ МЕТОДЫ ДЛЯ РЕАКЦИЙ ============
    
    def init_reactions_table(self):
        """Инициализация таблицы реакций"""
        pass
    
    def get_user_reaction(self, message_id: int, user_id: int):
        """Получить реакцию пользователя на сообщение"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT reaction FROM message_reactions WHERE message_id = ? AND user_id = ?',
                (message_id, user_id)
            )
            result = cursor.fetchone()
            return result[0] if result else None
    
    def save_reaction(self, message_id: int, user_id: int, author_id: int, reaction: int):
        """Сохранить новую реакцию"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO message_reactions (message_id, user_id, author_id, reaction, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (message_id, user_id, author_id, reaction, datetime.now(), datetime.now()))
            conn.commit()
    
    def update_reaction(self, message_id: int, user_id: int, new_reaction: int):
        """Обновить существующую реакцию"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE message_reactions 
                SET reaction = ?, updated_at = ?
                WHERE message_id = ? AND user_id = ?
            ''', (new_reaction, datetime.now(), message_id, user_id))
            conn.commit()
    
    def get_message_reaction_stats(self, message_id: int):
        """Получить статистику реакций для сообщения"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN reaction = 1 THEN 1 ELSE 0 END) as likes,
                    SUM(CASE WHEN reaction = -1 THEN 1 ELSE 0 END) as dislikes
                FROM message_reactions 
                WHERE message_id = ?
            ''', (message_id,))
            result = cursor.fetchone()
            return {'likes': result[0] or 0, 'dislikes': result[1] or 0}
    
    def get_user_total_reactions_given(self, user_id: int):
        """Получить общее количество реакций, поставленных пользователем"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM message_reactions WHERE user_id = ?', (user_id,))
            return cursor.fetchone()[0] or 0
    
    def get_user_total_reactions_received(self, user_id: int):
        """Получить общее количество реакций, полученных пользователем"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    SUM(CASE WHEN reaction = 1 THEN 1 ELSE 0 END) as likes,
                    SUM(CASE WHEN reaction = -1 THEN 1 ELSE 0 END) as dislikes
                FROM message_reactions 
                WHERE author_id = ?
            ''', (user_id,))
            result = cursor.fetchone()
            return {'likes': result[0] or 0, 'dislikes': result[1] or 0}
    
    def get_reaction_net_score(self, user_id: int):
        """Получить чистый счёт реакций пользователя"""
        stats = self.get_user_total_reactions_received(user_id)
        return stats['likes'] - stats['dislikes']

rating_db = RatingDB()
