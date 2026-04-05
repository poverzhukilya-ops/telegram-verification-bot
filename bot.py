# bot.py
import logging
import json
import os
import requests
import base64
import sqlite3
import time
from datetime import datetime
from typing import Dict, Optional
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from config import BOT_TOKEN, GROUP_ID, INVITE_LINK, ADMIN_ID, REGULATIONS_LINK, GROUPS_FILE, CHANNEL_LINK
from database import db
import threading
from rating_db import rating_db

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для разговора
STEP1_CAPTCHA = 1
STEP2_REGULATIONS = 2
ADD_GROUP_NAME = 3
ADD_GROUP_LINK = 4

# Хранилище для пользователей
verified_users = {}
user_states = {}

# ============ НАСТРОЙКИ СИСТЕМЫ РЕАКЦИЙ ============
# Позитивные эмодзи (3 штуки)
POSITIVE_EMOJIS = {'👍', '❤️', '🔥'}
# Негативные эмодзи (3 штуки)
NEGATIVE_EMOJIS = {'👎', '💩', '🤮'}

# Все поддерживаемые эмодзи
ALL_REACTION_EMOJIS = POSITIVE_EMOJIS.union(NEGATIVE_EMOJIS)

# Защита от спама (user_id -> время последней реакции)
user_reaction_cooldown = defaultdict(float)

# ============ ФУНКЦИИ ДЛЯ РАБОТЫ С РЕАКЦИЯМИ ============

def init_reactions_db():
    """Инициализация базы данных для реакций"""
    try:
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        
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
        conn.close()
        logger.info("✅ База данных реакций инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД реакций: {e}")

def get_user_reaction_on_message(user_id: int, message_id: int) -> Optional[str]:
    """Получить реакцию пользователя на сообщение (None если нет реакции)"""
    try:
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT reaction_type FROM user_reactions 
            WHERE user_id = ? AND message_id = ?
        ''', (user_id, message_id))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Ошибка получения реакции: {e}")
        return None

def save_user_reaction(user_id: int, message_id: int, reaction_type: str):
    """Сохранить или обновить реакцию пользователя"""
    try:
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        
        now = datetime.now()
        cursor.execute('''
            INSERT INTO user_reactions (user_id, message_id, reaction_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, message_id) 
            DO UPDATE SET reaction_type = ?, updated_at = ?
        ''', (user_id, message_id, reaction_type, now, now, reaction_type, now))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения реакции: {e}")

def delete_user_reaction(user_id: int, message_id: int):
    """Удалить реакцию пользователя"""
    try:
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM user_reactions WHERE user_id = ? AND message_id = ?
        ''', (user_id, message_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка удаления реакции: {e}")

def save_message_author(message_id: int, author_id: int):
    """Сохраняет автора сообщения"""
    try:
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO rated_messages (message_id, author_id, created_at)
            VALUES (?, ?, ?)
        ''', (message_id, author_id, datetime.now()))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Ошибка сохранения автора сообщения: {e}")

def get_message_author(message_id: int) -> Optional[int]:
    """Получить автора сообщения"""
    try:
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        cursor.execute('SELECT author_id FROM rated_messages WHERE message_id = ?', (message_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Ошибка получения автора: {e}")
        return None

def get_message_reaction_score(message_id: int) -> tuple:
    """Получить суммарный счёт сообщения (лайки, дизлайки, общий счёт)"""
    try:
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(CASE WHEN reaction_type IN ('👍', '❤️', '🔥') THEN 1 END) as likes,
                COUNT(CASE WHEN reaction_type IN ('👎', '💩', '🤮') THEN 1 END) as dislikes
            FROM user_reactions
            WHERE message_id = ?
        ''', (message_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        likes = result[0] or 0
        dislikes = result[1] or 0
        total_score = (likes * 10) - (dislikes * 10)
        
        return likes, dislikes, total_score
    except Exception as e:
        logger.error(f"Ошибка получения счёта сообщения: {e}")
        return 0, 0, 0

def update_user_rating_reaction(user_id: int, delta: int, reason: str):
    """Обновляет рейтинг пользователя через rating_db"""
    try:
        # Используем существующую функцию rating_db.update_rating
        rating_db.update_rating(user_id, delta, reason)
        logger.info(f"📊 Рейтинг пользователя {user_id}: {delta:+d} очков. Причина: {reason}")
    except Exception as e:
        logger.error(f"Ошибка обновления рейтинга: {e}")

# ============ ФУНКЦИЯ СОХРАНЕНИЯ РЕЙТИНГА В GITHUB ============
def save_rating_to_github():
    """Сохраняет рейтинг в GitHub репозиторий"""
    try:
        # Получаем список рейтинга
        rating_list = rating_db.get_rating_list(100)
        result = []
        
        for idx, user in enumerate(rating_list, 1):
            result.append({
                'position': idx,
                'user_id': user[0],
                'username': user[1] or f"user_{user[0]}",
                'name': f"{user[2]} {user[3] or ''}".strip(),
                'points': user[4],
                'level': user[5],
                'projects': user[6] + user[7],
                'investments': user[8],
                'reputation': user[10] if len(user) > 10 else 0
            })
        
        # Формируем JSON
        data = {
            'success': True,
            'data': result,
            'total': len(result),
            'updated_at': datetime.now().isoformat()
        }
        
        content = json.dumps(data, ensure_ascii=False, indent=2)
        
        # GitHub API
        github_token = os.environ.get('GITHUB_TOKEN')
        if not github_token:
            logger.warning("GITHUB_TOKEN не установлен")
            return False
            
        url = "https://api.github.com/repos/poverzhukilya-ops/telegram-verification-bot/contents/data/rating.json"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        
        # Получаем текущий файл
        response = requests.get(url, headers=headers)
        sha = response.json().get('sha') if response.status_code == 200 else None
        
        # Подготовка данных
        commit_data = {
            "message": f"Update rating {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "content": base64.b64encode(content.encode('utf-8')).decode('utf-8'),
            "sha": sha
        }
        
        # Отправляем
        result_put = requests.put(url, headers=headers, json=commit_data)
        
        if result_put.status_code in [200, 201]:
            logger.info(f"✅ Рейтинг сохранен в GitHub: {len(result)} участников")
            return True
        else:
            logger.error(f"❌ Ошибка GitHub API: {result_put.status_code}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        return False

# ============ ОБРАБОТЧИК РЕАКЦИЙ ============

async def handle_message_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик реакций на сообщения"""
    try:
        # Получаем данные о реакции
        reaction_update = update.message_reaction
        if not reaction_update:
            return
        
        message_id = reaction_update.message_id
        chat_id = reaction_update.chat.id
        reactor_id = reaction_update.user_id  # Кто поставил реакцию
        
        # Игнорируем реакции от бота
        if reactor_id == context.bot.id:
            return
        
        # Получаем сообщение и его автора
        try:
            message = await context.bot.get_messages(chat_id, message_id)
            if not message or not message.from_user:
                return
            author_id = message.from_user.id
        except Exception as e:
            logger.error(f"❌ Ошибка получения сообщения {message_id}: {e}")
            return
        
        # Нельзя оценивать свои сообщения
        if reactor_id == author_id:
            # Удаляем реакцию
            try:
                await context.bot.delete_message_reaction(chat_id, message_id, reactor_id)
            except:
                pass
            return
        
        # Сохраняем автора сообщения в БД (если ещё не сохранён)
        save_message_author(message_id, author_id)
        
        # Защита от спама (не чаще 1 реакции в 2 секунды)
        current_time = time.time()
        if current_time - user_reaction_cooldown[reactor_id] < 2:
            return
        user_reaction_cooldown[reactor_id] = current_time
        
        # Определяем тип реакции
        if not reaction_update.new_reactions:
            # Пользователь убрал реакцию - откатываем очки
            old_reaction = get_user_reaction_on_message(reactor_id, message_id)
            if old_reaction:
                # Удаляем реакцию из БД
                delete_user_reaction(reactor_id, message_id)
                
                # Откатываем очки автора
                if old_reaction in POSITIVE_EMOJIS:
                    update_user_rating_reaction(author_id, -10, f"Пользователь {reactor_id} убрал лайк с сообщения {message_id}")
                    logger.info(f"➖ Лайк убран с сообщения {message_id}, у автора -10 очков")
                elif old_reaction in NEGATIVE_EMOJIS:
                    update_user_rating_reaction(author_id, +10, f"Пользователь {reactor_id} убрал дизлайк с сообщения {message_id}")
                    logger.info(f"➕ Дизлайк убран с сообщения {message_id}, у автора +10 очков")
            return
        
        # Получаем новую реакцию
        reaction_emoji = reaction_update.new_reactions[0].emoji
        
        # Проверяем, поддерживается ли реакция
        if reaction_emoji not in ALL_REACTION_EMOJIS:
            # Удаляем неподдерживаемую реакцию
            try:
                await context.bot.delete_message_reaction(chat_id, message_id, reactor_id)
            except:
                pass
            return
        
        # Определяем тип и количество очков
        is_positive = reaction_emoji in POSITIVE_EMOJIS
        new_delta = 10 if is_positive else -10
        
        # Проверяем, была ли уже реакция от этого пользователя
        old_reaction = get_user_reaction_on_message(reactor_id, message_id)
        
        if old_reaction:
            old_is_positive = old_reaction in POSITIVE_EMOJIS
            old_delta = 10 if old_is_positive else -10
            
            if old_reaction == reaction_emoji:
                # Та же реакция - игнорируем
                return
            else:
                # Пользователь меняет реакцию (лайк на дизлайк или наоборот)
                # Сначала откатываем старую
                update_user_rating_reaction(author_id, -old_delta, f"Пользователь {reactor_id} изменил реакцию на сообщении {message_id}")
                # Затем начисляем новую
                update_user_rating_reaction(author_id, new_delta, f"Пользователь {reactor_id} изменил реакцию на сообщении {message_id}")
                
                # Обновляем реакцию в БД
                save_user_reaction(reactor_id, message_id, reaction_emoji)
                
                logger.info(f"🔄 Реакция изменена! Теперь {'+10' if is_positive else '-10'} очков автору {author_id}")
                return
        
        # Новая реакция - сохраняем и начисляем очки
        save_user_reaction(reactor_id, message_id, reaction_emoji)
        update_user_rating_reaction(author_id, new_delta, f"Пользователь {reactor_id} поставил {reaction_emoji} на сообщение {message_id}")
        
        # Сохраняем рейтинг в GitHub после каждого изменения (но не слишком часто)
        # Для оптимизации можно сохранять раз в минуту, но для простоты сохраняем сразу
        save_rating_to_github()
        
        # Получаем общую статистику сообщения для лога
        likes, dislikes, total = get_message_reaction_score(message_id)
        logger.info(f"📊 РЕАКЦИЯ: {reaction_emoji} от {reactor_id} на сообщение {message_id} автора {author_id} -> {new_delta:+d} очков (Всего: 👍{likes} 👎{dislikes} = {total:+d})")
        
    except Exception as e:
        logger.error(f"❌ Ошибка в обработчике реакций: {e}")

# ============ КОМАНДЫ ДЛЯ РАБОТЫ С РЕАКЦИЯМИ ============

async def my_rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /my_rating - показать свой рейтинг и статистику реакций"""
    user_id = update.effective_user.id
    
    try:
        # Получаем рейтинг через rating_db
        rating = rating_db.get_user_rating(user_id)
        
        # Получаем статистику реакций из БД
        conn = sqlite3.connect('rating.db')
        cursor = conn.cursor()
        
        # Статистика поставленных реакций
        cursor.execute('''
            SELECT 
                COUNT(CASE WHEN reaction_type IN ('👍', '❤️', '🔥') THEN 1 END) as likes_given,
                COUNT(CASE WHEN reaction_type IN ('👎', '💩', '🤮') THEN 1 END) as dislikes_given
            FROM user_reactions
            WHERE user_id = ?
        ''', (user_id,))
        
        given = cursor.fetchone()
        likes_given = given[0] or 0
        dislikes_given = given[1] or 0
        
        # Статистика полученных реакций
        cursor.execute('''
            SELECT 
                COUNT(CASE WHEN reaction_type IN ('👍', '❤️', '🔥') THEN 1 END) as likes_received,
                COUNT(CASE WHEN reaction_type IN ('👎', '💩', '🤮') THEN 1 END) as dislikes_received
            FROM user_reactions ur
            JOIN rated_messages rm ON ur.message_id = rm.message_id
            WHERE rm.author_id = ?
        ''', (user_id,))
        
        received = cursor.fetchone()
        likes_received = received[0] or 0
        dislikes_received = received[1] or 0
        
        conn.close()
        
        await update.message.reply_text(
            f"📊 *Ваш рейтинг и статистика*\n\n"
            f"🏆 *Рейтинг:* {rating} очков\n\n"
            f"📤 *Вы оценили других:*\n"
            f"   👍 Лайков: {likes_given}\n"
            f"   👎 Дизлайков: {dislikes_given}\n\n"
            f"📥 *Другие оценили вас:*\n"
            f"   👍 Лайков: {likes_received} (+{likes_received * 10} очков)\n"
            f"   👎 Дизлайков: {dislikes_received} (-{dislikes_received * 10} очков)\n\n"
            f"💡 *Как работает система:*\n"
            f"• Каждый лайк = +10 очков автору\n"
            f"• Каждый дизлайк = -10 очков автору\n"
            f"• Один пользователь = одна оценка на сообщение\n"
            f"• Можно изменить свою оценку",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка в my_rating_command: {e}")
        await update.message.reply_text("❌ Ошибка получения статистики")

async def message_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /message_stats - показать статистику сообщения (по reply)"""
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение, чтобы увидеть его статистику!")
        return
    
    target_message = update.message.reply_to_message
    message_id = target_message.message_id
    
    likes, dislikes, total = get_message_reaction_score(message_id)
    
    await update.message.reply_text(
        f"📊 *Статистика сообщения*\n\n"
        f"👤 Автор: {target_message.from_user.first_name}\n"
        f"👍 Лайков: {likes} (+{likes * 10} очков)\n"
        f"👎 Дизлайков: {dislikes} (-{dislikes * 10} очков)\n"
        f"📈 Общий счёт: {total:+d} очков\n\n"
        f"📝 Текст: {target_message.text[:100] if target_message.text else '[медиа/файл]'}",
        parse_mode='Markdown'
    )

# ============ ОСТАЛЬНОЙ КОД (БЕЗ ИЗМЕНЕНИЙ) ============

# Загрузка групп из файла
def load_groups() -> Dict[str, str]:
    """Загружает группы из JSON файла"""
    if os.path.exists(GROUPS_FILE):
        try:
            with open(GROUPS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки групп: {e}")
    return {}

def save_groups(groups: Dict[str, str]):
    """Сохраняет группы в JSON файл"""
    try:
        with open(GROUPS_FILE, 'w', encoding='utf-8') as f:
            json.dump(groups, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения групп: {e}")

async def check_user_in_group(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    """Проверяет, состоит ли пользователь в группе"""
    try:
        member = await context.bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки членства для {user_id}: {e}")
        return False

async def clear_user_data(user_id: int, context: ContextTypes.DEFAULT_TYPE = None):
    """Полная очистка данных пользователя"""
    if user_id in verified_users:
        del verified_users[user_id]
    if user_id in user_states:
        del user_states[user_id]
    if context and context.user_data:
        context.user_data.clear()

async def delete_all_bot_messages(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Удаляет все сообщения бота в чате"""
    try:
        messages = await context.bot.get_chat_history(chat_id, limit=100)
        
        deleted_count = 0
        for message in messages:
            if message.from_user and message.from_user.id == context.bot.id:
                try:
                    await message.delete()
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Не удалось удалить сообщение {message.message_id}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Удалено {deleted_count} сообщений бота для чата {chat_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при получении истории сообщений: {e}")

async def send_projects_list(chat_id: int, context: ContextTypes.DEFAULT_TYPE, message_id: int = None, is_edit: bool = False):
    """Отправляет список проектов"""
    groups = load_groups()
    
    if not groups:
        text = "📁 *Список групп проектов*\n\nПока нет доступных групп."
    else:
        text = "📁 *Список групп проектов*\n\nВыберите группу для вступления:\n\n"
        for group_name, group_link in groups.items():
            text += f"• [{group_name}]({group_link})\n"
    
    keyboard = []
    keyboard.append([InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_projects")])
    keyboard.append([InlineKeyboardButton("➕ Добавить группу", callback_data="add_group")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_edit and message_id:
        try:
            await context.bot.edit_message_text(
                text=text,
                chat_id=chat_id,
                message_id=message_id,
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Ошибка при редактировании: {e}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )

async def groups_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /groups — показать список групп проектов"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if user_id not in verified_users:
        await update.message.reply_text(
            "❌ *Доступ запрещен!*\n\nСначала пройдите верификацию с помощью /start",
            parse_mode='Markdown'
        )
        return
    
    in_group = await check_user_in_group(context, user_id)
    
    if not in_group:
        join_count = verified_users[user_id].get('join_count', 1)
        if join_count >= 3:
            await update.message.reply_text(
                "🚫 *Доступ запрещен!*\n\nВы использовали все 3 попытки вступления.\nОбратитесь к администратору.",
                parse_mode='Markdown'
            )
            return
        else:
            await update.message.reply_text(
                f"⚠️ *Вы не в основной группе!*\n\nИспользовано попыток: {join_count} из 3\nОтправьте /start для повторной регистрации.",
                parse_mode='Markdown'
            )
            return
    
    await send_projects_list(chat_id, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start — начало регистрации"""
    user = update.effective_user
    user_id = user.id
    
    db.add_user(user_id, user.username, user.first_name, user.last_name)
    await clear_user_data(user_id, context)
    
    logger.info(f"Пользователь {user_id} (@{user.username}) начал регистрацию")
    
    intro_message = f"""
👋 *Привет, {user.first_name}!*

*Avantyurist* — сообщество для совместных проектов и инвестиций.

Для доступа нужно выполнить 2 простых шага:

1️⃣ Пройти проверку "Я не робот"
2️⃣ Ознакомиться с регламентом

Готовы?
"""
    
    keyboard = [[InlineKeyboardButton("▶️ Начать", callback_data="start_step1")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        intro_message,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    return STEP1_CAPTCHA

async def start_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1: Проверка на бота"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = query.from_user
    chat_id = query.message.chat_id
    
    in_group = await check_user_in_group(context, user_id)
    
    if user_id in verified_users and in_group:
        await query.edit_message_text(
            "✅ *Вы уже в группе!*\n\nДобро пожаловать в Avantyurist!\n\nИспользуйте кнопку меню внизу экрана или команду /groups для просмотра групп проектов.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    if user_id in verified_users and not in_group:
        join_count = verified_users[user_id].get('join_count', 1)
        
        if join_count >= 3:
            await clear_user_data(user_id, context)
            await query.edit_message_text(
                f"🚫 *Доступ запрещен!*\n\nВы использовали все {join_count} попытки вступления в группу.\n\nДля получения доступа обратитесь к администратору.",
                parse_mode='Markdown'
            )
            return ConversationHandler.END
        
        verified_users[user_id]['join_count'] = join_count + 1
        await delete_all_bot_messages(context, chat_id)
        
        remaining = 3 - (join_count + 1)
        attempts_message = f"\n\n*Осталось попыток: {remaining} из 3*" if remaining > 0 else "\n\n⚠️ *Это последняя попытка!*"
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔄 *Вы покинули группу*\n\nПопытка вступления #{join_count + 1}{attempts_message}\n\nДля повторного доступа пройдите верификацию заново:",
            parse_mode='Markdown'
        )
        
        keyboard = [[InlineKeyboardButton("✅ Я не робот", callback_data="captcha_passed")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text="🤖 *Шаг 1 из 2: Проверка*\n\nНажмите кнопку, чтобы подтвердить, что вы человек.",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        return STEP1_CAPTCHA
    
    keyboard = [[InlineKeyboardButton("✅ Я не робот", callback_data="captcha_passed")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🤖 *Шаг 1 из 2: Проверка*\n\nНажмите кнопку, чтобы подтвердить, что вы человек.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    return STEP1_CAPTCHA

async def captcha_passed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 1 завершён: капча пройдена"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id not in user_states:
        user_states[user_id] = {}
    user_states[user_id]['captcha_passed'] = True
    
    keyboard = [
        [InlineKeyboardButton("📖 Открыть регламент", url=REGULATIONS_LINK)],
        [InlineKeyboardButton("✅ Ознакомился, продолжить", callback_data="regulations_read")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📜 *Шаг 2 из 2: Ознакомление с регламентом*\n\n1️⃣ Нажмите кнопку ниже и прочитайте регламент\n2️⃣ После прочтения нажмите «Ознакомился, продолжить»",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    return STEP2_REGULATIONS

async def regulations_read(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Шаг 2: Подтверждение ознакомления с регламентом"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = query.from_user
    chat_id = query.message.chat_id
    
    if user_id not in user_states or not user_states[user_id].get('captcha_passed'):
        await query.answer("⚠️ Сначала пройдите проверку", show_alert=True)
        return STEP2_REGULATIONS
    
    verified_users[user_id] = {
        'username': user.username,
        'first_name': user.first_name,
        'verified_at': datetime.now().isoformat(),
        'regulations_read': True,
        'join_count': 1
    }
    
    # Добавляем в рейтинг
    rating_db.add_or_update_user(user_id, user.username, user.first_name, user.last_name)
    rating_db.update_rating(user_id, 'registration', 100, 'Бонус за регистрацию в сообществе')
    
    # СОХРАНЯЕМ РЕЙТИНГ В GITHUB
    save_rating_to_github()
    
    db.set_verified(user_id, True)
    db.update_user_status(user_id, "neutral", "Верифицирован через бота")
    
    await query.edit_message_text(
        "✅ *Отлично! Верификация пройдена!*\n\nТеперь вы можете вступить в сообщество.\n\n*Внимание!* У вас есть 3 попытки вступления.\nПосле 3-го выхода доступ будет закрыт.\n\nИспользуйте кнопку меню внизу экрана или команду /groups для просмотра групп проектов.\n\n📊 Команда /my_rating - посмотреть свой рейтинг и статистику реакций",
        parse_mode='Markdown'
    )
    
    await send_invite_link(query.message, user_id)
    
    await context.bot.send_message(
        ADMIN_ID,
        f"🆕 *Новый участник верифицирован!*\n\n┌ 📌 *ID:* `{user_id}`\n├ 👤 *Username:* @{user.username or 'нет'}\n├ 📛 *Имя:* {user.first_name}\n├ ⏰ *Время:* {datetime.now().strftime('%d.%m.%Y %H:%M')}\n└ 📖 *Ознакомился с регламентом:* ✅\n└ 🔄 *Попытки вступления:* 1 из 3",
        parse_mode='Markdown'
    )
    
    if user_id in user_states:
        del user_states[user_id]
    
    return ConversationHandler.END

async def send_invite_link(message, user_id: int):
    """Отправка пригласительных ссылок"""
    group_button = InlineKeyboardButton("🚪 Войти в группу", url=INVITE_LINK)
    channel_button = InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_LINK)
    
    keyboard = [[group_button], [channel_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        "🔗 *Добро пожаловать в Avantyurist!* 🎉\n\n📌 *Важные ссылки:*\n\n1️⃣ Вступите в основную группу сообщества\n2️⃣ Подпишитесь на канал с новостями и анонсами\n\nНажмите на кнопки ниже:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def refresh_projects(update: Update, context: ContextTypes.DEFAULT_TYPE):
