FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgomp1 \
    libjpeg-dev \
    zlib1g-dev \
    git git-lfs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения и .env
COPY app/ ./app/
COPY .env .env

# Команда запуска воркера
CMD ["python", "-m", "app.worker"]
