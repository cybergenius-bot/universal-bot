FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Нерутовый пользователь
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health/live" || exit 1

# Прод-старт без reload
CMD ["gunicorn","-k","uvicorn.workers.UvicornWorker","bot:app","--bind","0.0.0.0:${PORT:-8000}","--access-logfile","-","--error-logfile","-"]
