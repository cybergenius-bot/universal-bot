#!/bin/sh
set -euo pipefail
: "${PORT:=8000}" # Порт сервера
: "${MODE:=webhook}" # webhook | polling
: "${WORKERS:=1}" # Кол-во воркеров Gunicorn
: "${LOG_LEVEL:=info}" # debug|info|warning|error|critical
echo "[entrypoint] Preflight: проверка импорта bot:app..."
python - <<'PY'
import sys, importlib, os
print("cwd=", os.getcwd())
m = importlib.import_module("bot")
print("bot.file=", getattr(m, "file", None))
ok = hasattr(m, "app")
print("hasattr(bot,'app')=", ok)
if not ok: raise SystemExit("В модуле bot нет переменной 'app'. Проверьте имя и путь.")
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
