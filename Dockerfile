FROM python:3.11-slim
ENV PIP_NO_CACHE_DIR=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
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
Чиним возможные CRLF и ставим +x
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh || true && chmod +x /usr/local/bin/entrypoint.sh
Ловим синтаксические ошибки ещё на сборке
RUN python -m py_compile /app/bot.py /app/serve.py
Непривилегированный пользователь
RUN groupadd -g 1001 app && useradd -u 1001 -g app -m -s /bin/bash app && chown -R app:app /app
USER app
Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
CMD sh -lc 'curl -fsS "http://localhost😒{PORT:-8080}/health/live" || exit 1'
ENTRYPOINT
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
