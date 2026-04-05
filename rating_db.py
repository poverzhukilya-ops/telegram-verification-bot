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
            
            # ============ НОВЫЕ ТАБЛИЦЫ ДЛЯ СИСТЕМЫ РЕАКЦИЙ ============
            
            # Таблица для хранения реакций пользователей на сообщения
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message_id INTEGER,
                    reaction_type TEXT,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    UNIQUE(user_id, message_id)
                )
            ''')
            
            # Таблица для хранения информации о сообщениях (автор)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rated_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER UNIQUE,
                    author_id INTEGER,
                    created_at TIMESTAMP
                )
            ''')
            
            # Индексы для быстрого поиска
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_message_reactions ON user_reactions(message_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_reactions ON user_reactions(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_rated_messages ON rated_messages(message_id)')
            
            conn.commit()
            logger.info("База данных рейтинга инициализирована (включая систему реакций)")
    
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
    
    # ============ НОВЫЕ ФУНКЦИИ ДЛЯ СИСТЕМЫ РЕАКЦИЙ ============
    
    def save_user_reaction(self, user_id: int, message_id: int, reaction_type: str):
        """Сохранить или обновить реакцию пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                now = datetime.now()
                cursor.execute('''
                    INSERT INTO user_reactions (user_id, message_id, reaction_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, message_id) 
                    DO UPDATE SET reaction_type = ?, updated_at = ?
                ''', (user_id, message_id, reaction_type, now, now, reaction_type, now))
                conn.commit()
                logger.debug(f"Сохранена реакция {reaction_type} от {user_id} на сообщение {message_id}")
        except Exception as e:
            logger.error(f"Ошибка сохранения реакции: {e}")
    
    def delete_user_reaction(self, user_id: int, message_id: int):
        """Удалить реакцию пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    DELETE FROM user_reactions WHERE user_id = ? AND message_id = ?
                ''', (user_id, message_id))
                conn.commit()
                logger.debug(f"Удалена реакция от {user_id} на сообщение {message_id}")
        except Exception as e:
            logger.error(f"Ошибка удаления реакции: {e}")
    
    def get_user_reaction_on_message(self, user_id: int, message_id: int):
        """Получить реакцию пользователя на сообщение (None если нет реакции)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT reaction_type FROM user_reactions 
                    WHERE user_id = ? AND message_id = ?
                ''', (user_id, message_id))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения реакции: {e}")
            return None
    
    def save_message_author(self, message_id: int, author_id: int):
        """Сохраняет автора сообщения"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO rated_messages (message_id, author_id, created_at)
                    VALUES (?, ?, ?)
                ''', (message_id, author_id, datetime.now()))
                conn.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения автора сообщения: {e}")
    
    def get_message_author(self, message_id: int):
        """Получить автора сообщения"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT author_id FROM rated_messages WHERE message_id = ?', (message_id,))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Ошибка получения автора: {e}")
            return None
    
    def get_message_reaction_score(self, message_id: int):
        """Получить суммарный счёт сообщения (лайки, дизлайки, общий счёт)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Определяем позитивные и негативные эмодзи
                positive_emojis = ('👍', '❤️', '🔥')
                negative_emojis = ('👎', '💩', '🤮')
                
                cursor.execute('''
                    SELECT 
                        COUNT(CASE WHEN reaction_type IN (?, ?, ?) THEN 1 END) as likes,
                        COUNT(CASE WHEN reaction_type IN (?, ?, ?) THEN 1 END) as dislikes
                    FROM user_reactions
                    WHERE message_id = ?
                ''', (*positive_emojis, *negative_emojis, message_id))
                
                result = cursor.fetchone()
                
                likes = result[0] or 0
                dislikes = result[1] or 0
                total_score = (likes * 10) - (dislikes * 10)
                
                return likes, dislikes, total_score
        except Exception as e:
            logger.error(f"Ошибка получения счёта сообщения: {e}")
            return 0, 0, 0
    
    def get_user_reaction_stats(self, user_id: int):
        """Получить статистику реакций пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                positive_emojis = ('👍', '❤️', '🔥')
                negative_emojis = ('👎', '💩', '🤮')
                
                # Статистика поставленных реакций
                cursor.execute('''
                    SELECT 
                        COUNT(CASE WHEN reaction_type IN (?, ?, ?) THEN 1 END) as likes_given,
                        COUNT(CASE WHEN reaction_type IN (?, ?, ?) THEN 1 END) as dislikes_given
                    FROM user_reactions
                    WHERE user_id = ?
                ''', (*positive_emojis, *negative_emojis, user_id))
                
                given = cursor.fetchone()
                
                # Статистика полученных реакций
                cursor.execute('''
                    SELECT 
                        COUNT(CASE WHEN ur.reaction_type IN (?, ?, ?) THEN 1 END) as likes_received,
                        COUNT(CASE WHEN ur.reaction_type IN (?, ?, ?) THEN 1 END) as dislikes_received
                    FROM user_reactions ur
                    JOIN rated_messages rm ON ur.message_id = rm.message_id
                    WHERE rm.author_id = ?
                ''', (*positive_emojis, *negative_emojis, user_id))
                
                received = cursor.fetchone()
                
                return {
                    'likes_given': given[0] or 0,
                    'dislikes_given': given[1] or 0,
                    'likes_received': received[0] or 0,
                    'dislikes_received': received[1] or 0
                }
        except Exception as e:
            logger.error(f"Ошибка получения статистики реакций: {e}")
            return {
                'likes_given': 0,
                'dislikes_given': 0,
                'likes_received': 0,
                'dislikes_received': 0
            }
    
    def update_rating_by_reaction(self, user_id: int, delta: int, reason: str):
        """Обновляет рейтинг пользователя от реакции (лайк/дизлайк)"""
        try:
            # Используем существующую функцию update_rating
            # action_type = 'reaction_like' если delta > 0, иначе 'reaction_dislike'
            action_type = 'reaction_like' if delta > 0 else 'reaction_dislike'
            self.update_rating(user_id, action_type, delta, reason)
            logger.info(f"📊 Рейтинг пользователя {user_id} изменён на {delta:+d} очков. Причина: {reason}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления рейтинга от реакции: {e}")
            return False
    
    def get_top_rated_messages(self, limit=10):
        """Получить топ сообщений по количеству лайков"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                positive_emojis = ('👍', '❤️', '🔥')
                
                cursor.execute('''
                    SELECT 
                        message_id,
                        COUNT(*) as like_count
                    FROM user_reactions
                    WHERE reaction_type IN (?, ?, ?)
                    GROUP BY message_id
                    ORDER BY like_count DESC
                    LIMIT ?
                ''', (*positive_emojis, limit))
                
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Ошибка получения топ сообщений: {e}")
            return []
    
    def cleanup_old_reactions(self, days=30):
        """Очистка старых реакций (опционально)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cutoff_date = datetime.now().timestamp() - (days * 24 * 3600)
                cursor.execute('''
                    DELETE FROM user_reactions 
                    WHERE julianday('now') - julianday(created_at) > ?
                ''', (days,))
                deleted = cursor.rowcount
                conn.commit()
                logger.info(f"Очищено {deleted} старых реакций (старше {days} дней)")
                return deleted
        except Exception as e:
            logger.error(f"Ошибка очистки старых реакций: {e}")
            return 0

rating_db = RatingDB()
