# Базовый образ Python
FROM python:3.11-slim

# Устанавливаем ffmpeg и нужные системные зависимости
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем список зависимостей
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект в контейнер
COPY . .

# Запускаем бота через Uvicorn
CMD ["python", "run.py"]
