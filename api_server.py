from flask import Flask, jsonify, request
from flask_cors import CORS
from rating_db import rating_db
from database import db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Разрешаем запросы с сайта

# Секретный ключ для API (замени на свой)
API_KEY = "your_secret_api_key_here_change_me"

@app.route('/api/rating/<int:user_id>', methods=['GET'])
def get_user_rating(user_id):
    """Получить рейтинг конкретного пользователя"""
    try:
        rating_data = rating_db.get_user_rating(user_id)
        if rating_data:
            return jsonify({
                'success': True,
                'user_id': user_id,
                'username': rating_data[0],
                'first_name': rating_data[1],
                'last_name': rating_data[2],
                'points': rating_data[3],
                'level': rating_data[4],
                'projects_participated': rating_data[5],
                'projects_created': rating_data[6],
                'total_investments': rating_data[7],
                'reputation': rating_data[8]
            })
        else:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
    except Exception as e:
        logger.error(f"Error getting rating for {user_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rating/all', methods=['GET'])
def get_all_ratings():
    """Получить всех пользователей с рейтингом"""
    try:
        limit = request.args.get('limit', 100, type=int)
        rating_list = rating_db.get_rating_list(limit)
        
        result = []
        for idx, user in enumerate(rating_list, 1):
            result.append({
                'position': idx,
                'user_id': user[0],
                'username': user[1] or f"user_{user[0]}",
                'first_name': user[2],
                'last_name': user[3] or '',
                'points': user[4],
                'level': user[5],
                'projects_participated': user[6],
                'projects_created': user[7],
                'total_investments': user[8],
                'total_profit': user[9],
                'reputation': user[10]
            })
        
        return jsonify({
            'success': True,
            'total': len(result),
            'ratings': result
        })
    except Exception as e:
        logger.error(f"Error getting all ratings: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/rating/stats', methods=['GET'])
def get_rating_stats():
    """Получить общую статистику рейтинга"""
    try:
        stats = rating_db.get_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/message/<int:message_id>/reactions', methods=['GET'])
def get_message_reactions(message_id):
    """Получить статистику реакций для сообщения"""
    try:
        stats = rating_db.get_message_reaction_stats(message_id)
        return jsonify({
            'success': True,
            'message_id': message_id,
            'likes': stats['likes'],
            'dislikes': stats['dislikes'],
            'total': stats['likes'] + stats['dislikes'],
            'score': stats['likes'] - stats['dislikes']
        })
    except Exception as e:
        logger.error(f"Error getting message reactions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/user/<int:user_id>/reactions', methods=['GET'])
def get_user_reactions_stats(user_id):
    """Получить статистику реакций пользователя (полученных)"""
    try:
        stats = rating_db.get_user_total_reactions_received(user_id)
        net_score = rating_db.get_reaction_net_score(user_id)
        given = rating_db.get_user_total_reactions_given(user_id)
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'received': {
                'likes': stats['likes'],
                'dislikes': stats['dislikes']
            },
            'given': given,
            'net_score': net_score
        })
    except Exception as e:
        logger.error(f"Error getting user reactions stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Проверка работоспособности API"""
    return jsonify({'status': 'ok', 'message': 'API is running'})

if __name__ == '__main__':
    # Запускаем API сервер на порту 5000
    app.run(host='0.0.0.0', port=5000, debug=False)
