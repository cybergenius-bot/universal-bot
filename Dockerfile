FROM python:3.11-slim

# Устанавливаем ffmpeg и зависимости
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем проект
COPY . .

# Запуск приложения
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]

