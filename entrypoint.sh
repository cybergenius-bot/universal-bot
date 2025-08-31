#!/usr/bin/env sh
# EntryPoint with module auto-detection and optional debug mode
set -eu
[ "${DEBUG_ENTRYPOINT:-0}" = "1" ] && set -x

PORT="${PORT:-8080}"
MODE="${MODE:-webhook}"
LOG_LEVEL="${LOG_LEVEL:-info}"
WORKERS="${WORKERS:-1}"
THREADS="${THREADS:-8}"
TIMEOUT="${TIMEOUT:-120}"
GRACEFUL_TIMEOUT="${GRACEFUL_TIMEOUT:-30}"
KEEP_ALIVE="${KEEP_ALIVE:-65}"

echo "[entrypoint] starting"
echo "[entrypoint] PORT=${PORT} MODE=${MODE} LOG_LEVEL=${LOG_LEVEL} WORKERS=${WORKERS} THREADS=${THREADS}"
echo "[entrypoint] PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-<not-set>} DEBUG_ENTRYPOINT=${DEBUG_ENTRYPOINT:-0}"
echo "[entrypoint] python: $(python -V || true)"

echo "[entrypoint] ls -la /app:"; ls -la /app || true
[ -d /app/main ] && { echo "[entrypoint] /app/main:"; ls -la /app/main || true; }
[ -d /app/src ]  && { echo "[entrypoint] /app/src:";  ls -la /app/src  || true; }

APP_MODULE=""
if   [ -f /app/serve.py ];      then APP_MODULE="serve:app"
elif [ -f /app/main/serve.py ]; then APP_MODULE="main.serve:app"
elif [ -f /app/src/serve.py ];  then APP_MODULE="src.serve:app"
elif [ -f /app/bot.py ];        then APP_MODULE="bot:app"
elif [ -f /app/main/bot.py ];   then APP_MODULE="main.bot:app"
elif [ -f /app/src/bot.py ];    then APP_MODULE="src.bot:app"
else
  echo "[entrypoint] ERROR: cannot find serve.py or bot.py in /app, /app/main, /app/src"
  sleep 5
  exit 1
fi
echo "[entrypoint] Using APP_MODULE=${APP_MODULE}"

GUNICORN_CMD="gunicorn \
  --bind 0.0.0.0:${PORT} \
  --workers ${WORKERS} \
  --threads ${THREADS} \
  --timeout ${TIMEOUT} \
  --graceful-timeout ${GRACEFUL_TIMEOUT} \
  --keep-alive ${KEEP_ALIVE} \
  --log-level ${LOG_LEVEL} \
  --access-logfile - \
  -k uvicorn.workers.UvicornWorker \
  ${APP_MODULE}"

echo "[entrypoint] launching -> ${GUNICORN_CMD}"
exec sh -c "${GUNICORN_CMD}"
