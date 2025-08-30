#!/usr/bin/env sh
# Robust entrypoint with optional debug mode
set -eu

# Enable shell tracing in debug mode
if [ "${DEBUG_ENTRYPOINT:-0}" = "1" ]; then
  set -x
fi

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
echo "[entrypoint] PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-<not-set>}"
echo "[entrypoint] DEBUG_ENTRYPOINT=${DEBUG_ENTRYPOINT:-0}"

# Quick environment and filesystem sanity (useful in logs)
echo "[entrypoint] python: $(python -V)"
echo "[entrypoint] gunicorn: $(python -c 'import gunicorn,sys;print(getattr(gunicorn,\"__version__\",sys.version))' || echo 'n/a')"
echo "[entrypoint] fastapi import: $(python - <<'PY'
try:
    import fastapi, telegram, openai
    print("ok")
except Exception as e:
    print("fail:", e)
PY
)"
echo "[entrypoint] ls -la /app:"
ls -la /app || true

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
  serve:app"

echo "[entrypoint] launching -> ${GUNICORN_CMD}"

if [ "${DEBUG_ENTRYPOINT:-0}" = "1" ]; then
  # In debug mode do not exec: keep container alive even if gunicorn exits
  sh -c "${GUNICORN_CMD}" || echo "[entrypoint][debug] gunicorn exited with code $?"
  echo "[entrypoint][debug] sleeping to keep logs visible..."
  # Keep container alive for inspection
  sleep 3600
else
  # Normal mode
  exec sh -c "${GUNICORN_CMD}"
fi
