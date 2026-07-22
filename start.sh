#!/bin/bash
set -e

echo "=== Starting GlideCast ==="
echo "PORT: ${PORT}"
echo "DATABASE_URL set: $([ -n "$DATABASE_URL" ] && echo YES || echo NO)"
echo "DJANGO_SECRET_KEY set: $([ -n "$DJANGO_SECRET_KEY" ] && echo YES || echo NO)"

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Running collectstatic ==="
python manage.py collectstatic --noinput || echo "collectstatic failed, continuing anyway"

echo "=== Starting gunicorn on port ${PORT:-8080} ==="
exec gunicorn skiwax.wsgi --bind 0.0.0.0:${PORT:-8080} --log-file - --log-level debug
