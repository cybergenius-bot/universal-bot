FROM python:3.11-slim

# Корректный блок ENV (каждая пара отдельно или через \)
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Системные пакеты (один RUN с переносами через \)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    ffmpeg \
  && rm -rf /var/lib/apt/lists/*

# Python-зависимости
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Исходники
COPY . /app

# Непривилегированный пользователь
RUN groupadd -g 1001 app && useradd -u 1001 -g app -m -s /bin/bash app \
  && chown -R app:app /app
USER app

# Healthcheck (бьём в /health/live на текущем $PORT)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD sh -lc 'curl -fsS "http://localhost:${PORT:-8000}/health/live" || exit 1'

# Важно: shell-форма CMD, чтобы Railway подставил $PORT
CMD gunicorn -k uvicorn.workers.UvicornWorker bot:app --bind 0.0.0.0:${PORT:-8000} --access-logfile - --error-logfile -
