#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
gunicorn tesis.wsgi:application --bind 0.0.0.0:${PORT:-8000}
