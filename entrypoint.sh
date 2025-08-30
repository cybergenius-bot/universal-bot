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
serve.py

import logging
try:
from bot import app as app  # noqa: F401
logging.info("serve.py: импорт bot:app — OK")
except Exception as e:
logging.exception("serve.py: НЕ удалось импортировать bot:app: %s", e)
from fastapi import FastAPI
from fastapi.responses import JSONResponse
app = FastAPI(title="Telegram Bot (fallback)", version="0.0.2")
@app.get("/")
async def root():
    return {"message": "Fallback: bot:app не импортирован. Проверьте логи."}
@app.get("/health/live")
async def health_live():
    return {"status": "ok", "service": "fallback"}
@app.get("/health/ready")
async def health_ready():
    return JSONResponse({"status": "not_ready", "service": "fallback"}, status_code=503)
