#!/bin/bash
# start.sh

# Запускаем Flask API на порту 8080
python -m flask --app bot:api_app run --host=0.0.0.0 --port=8080 &

# Запускаем бота
python bot.py
