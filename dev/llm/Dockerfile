FROM python:3.11-slim

WORKDIR /app

# Установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения и .env
COPY app/ ./app/
COPY .env .env

# Команда запуска воркера
CMD ["python", "-m", "app.worker"]
