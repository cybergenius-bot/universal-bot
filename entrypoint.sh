#!/bin/sh
set -euo pipefail
: "${PORT:=8000}" # Порт сервера
: "${MODE:=webhook}" # webhook | polling
: "${WORKERS:=1}" # Кол-во воркеров Gunicorn
: "${LOG_LEVEL:=info}" # debug|info|warning|error|critical
Предстартовая проверка: убедимся, что модуль bot импортируется и в нём есть app
echo "[entrypoint] Preflight: проверка импорта bot:app..."
python - <<'PY'
import sys, importlib, os, traceback
try:
print("cwd=", os.getcwd())
print("sys.path[0]=", sys.path[0] if sys.path else None)
m = importlib.import_module("bot")
print("bot.__file__=", getattr(m, "__file__", None))
ok = hasattr(m, "app")
print("hasattr(bot,'app')=", ok)
if not ok:
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
