#!/usr/bin/env bash
set -o errexit

export DJANGO_DEBUG="${DJANGO_DEBUG:-false}"
export USE_WHITENOISE="${USE_WHITENOISE:-true}"

python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
