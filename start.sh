#!/bin/bash
python -m flask --app bot:api_app run --host=0.0.0.0 --port=$PORT &
python bot.py
