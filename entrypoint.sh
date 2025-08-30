#!/bin/sh
set -euo pipefail
: "${PORT:=8000}"
: "${MODE:=webhook}" # webhook | polling
: "${WORKERS:=1}"
: "${LOG_LEVEL:=info}" # debug|info|warning|error|critical
echo "[entrypoint] Запуск Gunicorn/Uvicorn (serve:app)..."
exec gunicorn --chdir /app -k uvicorn.workers.UvicornWorker "serve:app" \
--bind "0.0.0.0:${PORT}" \
--workers "${WORKERS}" \
--timeout 120 \
--graceful-timeout 30 \
--log-level "${LOG_LEVEL}" \
--access-logfile - \
--error-logfile -
serve.py

import logging, traceback
from typing import Optional
try:
# Пытаемся использовать основное приложение
from bot import app as app  # noqa
logging.info("serve.py: импорт bot:app — OK")
except Exception as e:
# Если импорт не удался — поднимаем fallback, чтобы контейнер не падал
logging.exception("serve.py: НЕ удалось импортировать bot:app: %s", e)
from fastapi import FastAPI
from fastapi.responses import JSONResponse
app = FastAPI(title="Telegram Bot (fallback)", version="0.0.1")
@app.get("/")
async def root():
    return {"message": "Fallback: бот не запущен из-за ошибки импорта bot:app. Проверьте логи."}
@app.get("/health/live")
async def health_live():
    return {"status": "ok", "service": "fallback"}
@app.get("/health/ready")
async def health_ready():
    # Отдаём 503, чтобы видно было, что бот не готов
    return JSONResponse({"status": "not_ready", "service": "fallback"}, status_code=503)
Dockerfile

FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV PYTHONPATH=/app
WORKDIR /app
ARG DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
apt-get update; \
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  ffmpeg \
; \
update-ca-certificates; \
rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
Проверка синтаксиса (важно!) — ловим ошибки ещё на сборке
RUN python -m py_compile /app/bot.py /app/serve.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
RUN groupadd -g 1001 app && useradd -u 1001 -g app -m -s /bin/bash app && chown -R app:app /app
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
CMD sh -lc 'curl -fsS "http://localhost:$PORT/health/live" || exit 1'
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
