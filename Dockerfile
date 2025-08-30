FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 ENV PYTHONUNBUFFERED=1 ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends
gcc curl ffmpeg
&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt . RUN pip install --upgrade pip setuptools wheel
&& pip install --no-cache-dir -r requirements.txt

COPY . .
