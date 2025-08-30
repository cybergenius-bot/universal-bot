FROM python:3.11-slim

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Системные пакеты (исправлено: многострочный RUN с \)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ffmpeg \
  && rm -rf /var/lib/apt/lists/*

# Установка Python-зависимостей
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Копируем исходники
COPY . /app

# Непривилегированный пользователь
RUN addgroup --gid 1001 app && adduser --uid 1001 --disabled-password --gecos "" --home /home/app --ingroup app app \
  && chown -R app:app /app
USER app

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/live || exit 1

# Важно: shell-форма CMD, чтобы подставлялся $PORT на Railway
CMD gunicorn -k uvicorn.workers.UvicornWorker bot:app --bind 0.0.0.0:${PORT:-8000} --access-logfile - --error-logfile -
Файл: .dockerignore
