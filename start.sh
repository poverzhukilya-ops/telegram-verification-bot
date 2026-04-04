#!/bin/bash
# Запускаем Flask API
gunicorn --bind 0.0.0.0:8080 bot:api_app &

# Запускаем бота
python bot.py
