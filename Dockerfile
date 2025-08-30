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

