FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV PYTHONPATH=/app
WORKDIR /app
ARG DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
apt-get update; \
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  ffmpeg \
; \
update-ca-certificates; \
rm -rf /var/lib/apt/lists/*
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app
Проверка синтаксиса Python-кода на этапе сборки (важно!)
RUN python -m py_compile /app/bot.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
RUN groupadd -g 1001 app && useradd -u 1001 -g app -m -s /bin/bash app && chown -R app:app /app
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
CMD sh -lc 'curl -fsS "http://localhost:$PORT/health/live" || exit 1'
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
