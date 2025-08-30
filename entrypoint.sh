#!/bin/sh
set -euo pipefail
: "${PORT:=8000}"
: "${MODE:=webhook}" # webhook | polling
: "${WORKERS:=1}"
: "${LOG_LEVEL:=info}" # debug|info|warning|error|critical
if [ "$MODE" = "webhook" ]; then
exec gunicorn -k uvicorn.workers.UvicornWorker "bot:app" \
--bind "0.0.0.0:${PORT}" \
--workers "${WORKERS}" \
--timeout 120 \
--graceful-timeout 30 \
--log-level "${LOG_LEVEL}" \
--access-logfile - \
--error-logfile -
else
exec python bot.py
fi
