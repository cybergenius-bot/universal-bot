#!/bin/sh
set -euo pipefail
: "${PORT:=8000}"
: "${MODE:=webhook}"
: "${WORKERS:=1}"
: "${LOG_LEVEL:=info}"
echo "[entrypoint] PORT=
P
O
R
T
M
O
D
E
=
PORTMODE={MODE} WORKERS=
W
O
R
K
E
R
S
L
O
G
L
E
V
E
L
=
WORKERSLOG 
L
​
 EVEL={LOG_LEVEL}"
echo "[entrypoint] Запуск Gunicorn/Uvicorn (serve:app)..."
exec gunicorn --chdir /app -k uvicorn.workers.UvicornWorker "serve:app" \
--bind "0.0.0.0:${PORT}" \
--workers "${WORKERS}" \
--timeout 120 \
--graceful-timeout 30 \
--log-level "${LOG_LEVEL}" \
--access-logfile - \
--error-logfile -
