#!/usr/bin/env sh set -e

PORT="${PORT:-8080}" MODE="${MODE:-webhook}" LOG_LEVEL="${LOG_LEVEL:-info}" WORKERS="${WORKERS:-1}" THREADS="${THREADS:-8}" TIMEOUT="${TIMEOUT:-120}" GRACEFUL_TIMEOUT="${GRACEFUL_TIMEOUT:-30}" KEEP_ALIVE="${KEEP_ALIVE:-65}"

echo "[entrypoint] Starting container" echo "[entrypoint] PORT=
P
O
R
T
M
O
D
E
=
PORTMODE={MODE} LOG_LEVEL=
L
O
G
L
E
V
E
L
W
O
R
K
E
R
S
=
LOG 
L
​
 EVELWORKERS={WORKERS} THREADS=${THREADS}" echo "[entrypoint] PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-}" echo "[entrypoint] launching gunicorn -> serve:app"

exec gunicorn
--bind "0.0.0.0:${PORT}"
--workers "${WORKERS}"
--threads "${THREADS}"
--timeout "${TIMEOUT}"
--graceful-timeout "${GRACEFUL_TIMEOUT}"
--keep-alive "${KEEP_ALIVE}"
--log-level "${LOG_LEVEL}"
--access-logfile -
-k uvicorn.workers.UvicornWorker
serve:app
