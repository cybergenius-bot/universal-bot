# Базовый образ Python 3.11
FROM python:3.11-slim

# Устанавливаем системные пакеты (включая ffmpeg)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем список зависимостей
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код бота
COPY . .

# Запускаем сервер (порт берём из переменной Railway)
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
