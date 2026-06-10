#!/usr/bin/env bash
set -o errexit
set -o pipefail

export PORT="${PORT:-8000}"

python - <<'PY'
import os
import time

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tesis.settings")

import django
django.setup()

from django.db import connection
from django.db.utils import OperationalError

max_attempts = 15
for attempt in range(1, max_attempts + 1):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        print("Base de datos lista y extensión PostGIS verificada.", flush=True)
        break
    except OperationalError as exc:
        if attempt == max_attempts:
            raise
        print(f"Esperando a la base de datos ({attempt}/{max_attempts}): {exc}", flush=True)
        time.sleep(2)
PY

python manage.py migrate --noinput
exec gunicorn tesis.wsgi:application \
  --bind 0.0.0.0:${PORT} \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
