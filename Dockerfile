FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn skiwax.wsgi --bind 0.0.0.0:${PORT:-8080} --log-file -
