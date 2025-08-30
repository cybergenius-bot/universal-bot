#!/bin/sh
set -euo pipefail
: "${PORT:=8000}" # Порт сервера
: "${MODE:=webhook}" # webhook | polling
: "${WORKERS:=1}" # Кол-во воркеров Gunicorn
: "${LOG_LEVEL:=info}" # debug|info|warning|error|critical
echo "[entrypoint] Preflight: проверка импорта bot:app..."
python - <<'PY'
import sys, importlib, os, traceback
try:
print("cwd=", os.getcwd())
m = importlib.import_module("bot")
print("bot.__file__=", getattr(m, "__file__", None))
if not hasattr(m, "app"):
    raise AttributeError("В модуле bot нет переменной 'app'. Проверьте имя переменной (app/application) и путь.")
except Exception as e:
print("[entrypoint] ОШИБКА импортирования bot:app:", e)
traceback.print_exc()
sys.exit(97)
PY
if [ "$MODE" = "webhook" ]; then
echo "[entrypoint] Режим: webhook. Запуск Gunicorn/Uvicorn..."
exec gunicorn --chdir /app -k uvicorn.workers.UvicornWorker "bot:app" \
--bind "0.0.0.0:${PORT}" \
--workers "${WORKERS}" \
--timeout 120 \
--graceful-timeout 30 \
--log-level "${LOG_LEVEL}" \
--access-logfile - \
--error-logfile -
else
echo "[entrypoint] Режим: polling. Запуск python bot.py..."
exec python bot.py
fi
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
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
RUN groupadd -g 1001 app && useradd -u 1001 -g app -m -s /bin/bash app && chown -R app:app /app
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
CMD sh -lc 'curl -fsS "http://localhost:$PORT/health/live" || exit 1'
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
