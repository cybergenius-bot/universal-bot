FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Системные пакеты: gcc для сборки; curl для healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Копируем исходники
COPY . .

# Нерутовый пользователь
RUN useradd --create-home --shell /bin/bash app
USER app

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/health/live" || exit 1

# Старт uvicorn; Railway прокинет PORT
CMD ["sh", "-c", "python -m uvicorn bot:app --host 0.0.0.0 --port ${PORT:-8000}"]
