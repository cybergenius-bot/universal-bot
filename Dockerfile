# Базовый образ Python
FROM python:3.11-slim

# Устанавливаем ffmpeg и зависимости
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект
COPY . .

# Запуск бота
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
