# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/main:/app/src

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Ensure LF endings and executable bit for entrypoint
RUN sed -i 's/\r$//' /app/entrypoint.sh || true && \
    cp /app/entrypoint.sh /usr/local/bin/entrypoint.sh && \
    chmod +x /usr/local/bin/entrypoint.sh

# Catch syntax errors at build time
RUN python -c 'import compileall,sys; sys.exit(0 if compileall.compile_dir("/app", force=True, quiet=1) else 1)'

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD sh -lc 'curl -fsS "http://localhost:${PORT:-8080}/health/live" || exit 1'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
