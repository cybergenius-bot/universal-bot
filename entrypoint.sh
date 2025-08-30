#!/usr/bin/env sh
set -e
PORT="${PORT:-8080}"
MODE="${MODE:-webhook}"
LOG_LEVEL="${LOG_LEVEL:-info}"
WORKERS="${WORKERS:-1}"
THREADS="${THREADS:-8}"
TIMEOUT="${TIMEOUT:-120}"
GRACEFUL_TIMEOUT="${GRACEFUL_TIMEOUT:-30}"
KEEP_ALIVE="${KEEP_ALIVE:-65}"
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
 EVELWORKERS={WORKERS} THREADS=${THREADS}"
echo "[entrypoint] PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-}"
echo "[entrypoint] launching gunicorn -> serve:app"
exec gunicorn --bind "0.0.0.0:
P
O
R
T
"
−
−
w
o
r
k
e
r
s
"
PORT"−−workers"{WORKERS}" --threads "
T
H
R
E
A
D
S
"
−
−
t
i
m
e
o
u
t
"
THREADS"−−timeout"{TIMEOUT}" --graceful-timeout "
G
R
A
C
E
F
U
L
T
I
M
E
O
U
T
"
−
−
k
e
e
p
−
a
l
i
v
e
"
GRACEFUL 
T
​
 IMEOUT"−−keep−alive"{KEEP_ALIVE}" --log-level "${LOG_LEVEL}" -k uvicorn.workers.UvicornWorker serve:app
