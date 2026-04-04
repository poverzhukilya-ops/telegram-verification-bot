# bot.py
import logging
import json
import os
from datetime import datetime
from typing import Dict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from config import BOT_TOKEN, GROUP_ID, INVITE_LINK, ADMIN_ID, REGULATIONS_LINK, GROUPS_FILE, CHANNEL_LINK
from database import db
from flask import Flask, jsonify, request
from flask_cors import CORS
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
    
    db.set_verified(user_id, True)
    db.update_user_status(user_id, "neutral", "Верифицирован через бота")
    
    await query.edit_message_text(
        "✅ *Отлично! Верификация пройдена!*\n\nТеперь вы можете вступить в сообщество.\n\n*Внимание!* У вас есть 3 попытки вступления.\nПосле 3-го выхода доступ будет закрыт.\n\nИспользуйте кнопку меню внизу экрана или команду /groups для просмотра групп проектов.",
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
    """Обновление списка проектов"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    if user_id not in verified_users:
        await query.edit_message_text(
            "❌ *Доступ запрещен!*\n\nСначала пройдите верификацию с помощью /start",
            parse_mode='Markdown'
        )
        return
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")
    
    await send_projects_list(chat_id, context)

async def add_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало добавления группы (только для админа)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.edit_message_text(
            "🚫 *Доступ запрещен!*\n\nТолько администратор может добавлять группы.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    await query.edit_message_text(
        "📝 *Добавление новой группы проекта*\n\nВведите название группы:",
        parse_mode='Markdown'
    )
    
    return ADD_GROUP_NAME

async def add_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение названия группы"""
    group_name = update.message.text.strip()
    context.user_data['new_group_name'] = group_name
    
    await update.message.reply_text(
        f"📝 Название: *{group_name}*\n\nТеперь отправьте ссылку-приглашение в группу:",
        parse_mode='Markdown'
    )
    
    return ADD_GROUP_LINK

async def add_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение ссылки и сохранение группы"""
    group_link = update.message.text.strip()
    group_name = context.user_data.get('new_group_name')
    
    if not group_name:
        await update.message.reply_text("❌ Ошибка! Название группы не найдено.\nПопробуйте снова через меню.")
        return ConversationHandler.END
    
    if not (group_link.startswith('https://t.me/') or group_link.startswith('http://t.me/')):
        await update.message.reply_text(
            "❌ Неверный формат ссылки!\n\nСсылка должна быть вида: https://t.me/+XXXXXXXXXX\nПопробуйте снова:",
            parse_mode='Markdown'
        )
        return ADD_GROUP_LINK
    
    groups = load_groups()
    groups[group_name] = group_link
    save_groups(groups)
    
    await update.message.reply_text(
        f"✅ *Группа успешно добавлена!*\n\n📁 Название: {group_name}\n🔗 Ссылка: {group_link}\n\nТеперь она доступна в списке групп (/groups).",
        parse_mode='Markdown'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка статуса"""
    user_id = update.effective_user.id
    in_group = await check_user_in_group(context, user_id)
    
    if user_id in verified_users and in_group:
        data = verified_users[user_id]
        join_count = data.get('join_count', 1)
        remaining = 3 - join_count
        
        await update.message.reply_text(
            f"✅ *Вы верифицированы и в группе!*\n\n📅 Дата: {data['verified_at']}\n📖 Регламент: ✅ Ознакомились\n🔄 Использовано попыток: {join_count} из 3\n📊 Осталось: {remaining}\n\n📁 Используйте команду /groups для просмотра групп проектов.",
            parse_mode='Markdown'
        )
    elif user_id in verified_users:
        join_count = verified_users[user_id].get('join_count', 1)
        remaining = 3 - join_count
        
        if remaining > 0:
            await update.message.reply_text(
                f"⚠️ *Вы вышли из группы*\n\n🔄 Использовано попыток: {join_count} из 3\n📊 Осталось попыток: {remaining}\n\nОтправьте /start для повторной регистрации.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "🚫 *Доступ запрещен!*\n\nВы использовали все 3 попытки вступления.\nОбратитесь к администратору.",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            "❌ *Вы ещё не прошли верификацию.*\n\nОтправьте /start для начала регистрации.",
            parse_mode='Markdown'
        )

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправка ссылки на регламент"""
    keyboard = [[InlineKeyboardButton("📖 Регламент", url=REGULATIONS_LINK)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📜 *Ознакомьтесь с регламентом:*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Информация о сообществе"""
    await update.message.reply_text(
        "🌟 *Avantyurist* — сообщество инициативных людей.\n\nСовместные проекты, инвестиции, развитие.\n\n" + f"[Регламент]({REGULATIONS_LINK})",
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Справка"""
    help_text = """
📖 *Команды:*

/start — регистрация
/status — проверить статус
/groups — список групп проектов
/rules — регламент
/about — о сообществе
/help — справка

💡 *Совет:* Используйте кнопку меню внизу экрана для быстрого доступа к командам!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ============ API ДЛЯ РЕЙТИНГА ============

api_app = Flask(__name__)
CORS(api_app)

@api_app.route('/api/rating', methods=['GET'])
def get_rating():
    try:
        limit = request.args.get('limit', 50, type=int)
        rating_list = rating_db.get_rating_list(limit)
        
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
                'reputation': user[10]
            })
        
        return jsonify({'success': True, 'data': result, 'total': len(result)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        stats = rating_db.get_stats()
        return jsonify({'success': True, 'data': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def run_api_server():
    api_app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

# ============ КОНЕЦ API ============

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена регистрации"""
    user_id = update.effective_user.id
    await clear_user_data(user_id, context)
    
    await update.message.reply_text(
        "❌ Регистрация отменена.\nОтправьте /start для повторной попытки."
    )
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ошибок"""
    logger.error(f"Ошибка: {context.error}")

async def post_init(application: Application):
    """Функция, которая выполняется после запуска бота"""
    commands = [
        BotCommand("start", "🚀 Начать регистрацию"),
        BotCommand("groups", "📁 Группы проектов"),
        BotCommand("status", "📊 Проверить статус"),
        BotCommand("rules", "📖 Регламент"),
        BotCommand("about", "ℹ️ О сообществе"),
        BotCommand("help", "🆘 Помощь"),
    ]
    
    await application.bot.set_my_commands(commands)
    logger.info("✅ Кастомное меню команд установлено!")

def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            STEP1_CAPTCHA: [
                CallbackQueryHandler(start_step1, pattern='start_step1'),
                CallbackQueryHandler(captcha_passed, pattern='captcha_passed'),
            ],
            STEP2_REGULATIONS: [
                CallbackQueryHandler(regulations_read, pattern='regulations_read'),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('start', start),
        ],
        allow_reentry=True,
    )
    
    add_group_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_group_start, pattern='add_group')],
        states={
            ADD_GROUP_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_group_name)
            ],
            ADD_GROUP_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_group_link)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True,
    )
    
    application.add_handler(conv_handler)
    application.add_handler(add_group_handler)
    application.add_handler(CallbackQueryHandler(refresh_projects, pattern='refresh_projects'))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('groups', groups_command))
    application.add_handler(CommandHandler('rules', rules))
    application.add_handler(CommandHandler('about', about))
    application.add_handler(CommandHandler('help', help_command))
    application.add_error_handler(error_handler)
    
      print("🤖 Бот Avantyurist запущен!")
    print("📊 Лимит вступлений: 3 раза")
    print("📁 Кастомное меню установлено! Кнопка меню внизу экрана")
    print("📋 Команда /groups доступна в меню")
    print(f"🔗 Ссылка на группу: {INVITE_LINK}")
    print(f"📖 Регламент: {REGULATIONS_LINK}")
    
    application.run_polling()

if __name__ == '__main__':
    main()
