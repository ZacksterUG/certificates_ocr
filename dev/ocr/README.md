# OCR Worker (PaddleOCR-VL 1.5)

Микросервис для извлечения текста из изображений и PDF-сканов с использованием модели **PaddleOCR-VL 1.5**.

## Архитектура

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐      ┌──────────────┐
│   Backend   │─────▶│   RabbitMQ   │─────▶│ OCR Worker  │─────▶│   RabbitMQ   │
│  creates    │      │  ocr_tasks   │      │             │      │  llm_tasks   │
│ certificate │      │  (cert_id)   │      │             │      │              │
└─────────────┘      └──────────────┘      └──────┬──────┘      └──────────────┘
                                                  │
                                                  ▼
                                         ┌──────────────────┐
                                         │  PostgreSQL      │
                                         │  certificates    │
                                         │  (raw_text, etc) │
                                         └──────────────────┘
```

### Поток данных

1. **Бэкенд** создаёт запись в таблице `certificates` со статусом `pending`
2. Отправляет сообщение в очередь `ocr_tasks` (содержит `certificate_id` и `file_path`)
3. **OCR воркер** потребляет сообщение из очереди
4. Обрабатывает файл через модель **PaddleOCR-VL 1.5**
5. Обновляет запись в `certificates` (поле `raw_text`, статус `ocr_completed`)
6. Отправляет результат в очередь `llm_tasks` для дальнейшей обработки LLM

## Структура базы данных

### Таблица `certificates`

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | uuid | ID сертификата |
| `image_data` | varchar(500) | Путь к файлу изображения/PDF |
| `image_filename` | varchar(255) | Имя файла |
| `image_mime_type` | varchar(50) | MIME-тип файла |
| `image_size_bytes` | bigint | Размер файла в байтах |
| `raw_text` | text | **Распознанный текст (OCR)** |
| `ocr_confidence_score` | integer | **Точность распознавания (0-100)** |
| `ocr_page_count` | integer | **Количество страниц** |
| `ocr_processing_time_ms` | integer | **Время обработки OCR (мс)** |
| `structured_data` | jsonb | Результат обработки LLM |
| `status` | varchar(50) | Статус обработки |
| `error_message` | text | Сообщение об ошибке |
| `student_id` | varchar(100) | ID студента |
| `sent_to_llm` | boolean | **Отправлено в очередь LLM** |
| `created_at` | timestamp | Дата создания |
| `updated_at` | timestamp | Дата обновления |
| `completed_at` | timestamp | Дата завершения |

### Статусы обработки

| Статус | Описание |
|--------|----------|
| `pending` | Создан, ожидает обработки OCR |
| `ocr_processing` | Обрабатывается OCR |
| `ocr_completed` | OCR завершён, отправлено в LLM |
| `ocr_error` | Ошибка при обработке OCR |
| `llm_processing` | Обрабатывается LLM |
| `completed` | Полностью обработан |
| `error` | Ошибка обработки |

## Формат сообщений

### Очередь `ocr_tasks` (входная)

Бэкенд отправляет задачу на обработку:

```json
{
  "certificate_id": "550e8400-e29b-41d4-a716-446655440000",
  "file_path": "/app/datasets/certificate.pdf"
}
```

### Очередь `llm_tasks` (выходная)

Воркер отправляет результат OCR:

```json
{
  "certificate_id": "550e8400-e29b-41d4-a716-446655440000",
  "extracted_text": "South Ural State University\nCertificate of Attendance\nIVAN LYZHIN...",
  "confidence_score": 92,
  "page_count": 1,
  "file_name": "certificate.pdf",
  "created_at": "2026-03-04T10:00:00"
}
```

## Запуск

### Через Docker Compose

```bash
cd dev
docker-compose up -d ocr-service
```

### Проверка статуса

```bash
docker-compose logs -f ocr-service
```

## Конфигурация

### Переменные окружения (.env)

```bash
# ==================== Database ====================
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=certificates

# ==================== RabbitMQ ====================
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
OCR_QUEUE=ocr_tasks
LLM_QUEUE=llm_tasks

# ==================== PaddleOCR-VL Model ====================
# Локальный путь к модели (если пусто — загрузка из HuggingFace)
MODEL_PATH=/app/models/PaddleOCR-VL-1.5
# Имя модели в HuggingFace
MODEL_NAME=PaddlePaddle/PaddleOCR-VL-1.5
# Устройство: cpu или cuda
DEVICE=cpu
# Максимальное количество токенов в ответе
MAX_NEW_TOKENS=512

# ==================== Worker ====================
# Количество задач для одновременной обработки
PREFETCH_COUNT=1
# Режим отладки
DEBUG=false
```

### Загрузка модели

#### Вариант 1: Автоматическая загрузка (HuggingFace)

```bash
MODEL_PATH=
MODEL_NAME=PaddlePaddle/PaddleOCR-VL-1.5
```

Модель загружается при первом запуске контейнера (~6GB).

#### Вариант 2: Локальная модель (рекомендуется для production)

```bash
# Предварительно скачайте модель:
cd dev
mkdir -p models
git lfs install
git clone https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5 models/PaddleOCR-VL-1.5

# В .env укажите:
MODEL_PATH=/app/models/PaddleOCR-VL-1.5
```

**Преимущества локальной модели:**
- ✅ Быстрый старт контейнера
- ✅ Работа без доступа к интернету
- ✅ Контроль версий модели
- ✅ Кэширование между запусками

## Пример использования

### Отправка задачи из бэкенда (Python)

```python
import aio_pika
import json
import uuid

async def submit_certificate_for_ocr(file_path: str, file_name: str):
    # 1. Создаём запись в БД
    certificate_id = uuid.uuid4()
    # ... SQL INSERT INTO certificates ...
    
    # 2. Отправляем задачу в очередь OCR
    connection = await aio_pika.connect_robust("amqp://guest:guest@rabbitmq/")
    channel = await connection.channel()
    
    message = aio_pika.Message(
        body=json.dumps({
            "certificate_id": str(certificate_id),
            "file_path": file_path,
        }).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    
    await channel.default_exchange.publish(
        message, 
        routing_key="ocr_tasks"
    )
    
    await connection.close()
    return certificate_id
```

### Получение результата

```python
from sqlalchemy import create_engine, select
from app.models import Certificate

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/certificates")

with engine.connect() as conn:
    cert = conn.get(Certificate, certificate_id)
    print(f"Статус: {cert.status}")
    print(f"Текст: {cert.raw_text}")
    print(f"Точность: {cert.ocr_confidence_score}%")
```

## Поддерживаемые форматы

| Тип | Форматы |
|-----|---------|
| **Изображения** | PNG, JPG, JPEG, TIFF, BMP, WEBP |
| **Документы** | PDF (сканы изображений) |

## Производительность

| Устройство | Время на страницу |
|------------|-------------------|
| CPU | ~5-15 секунд |
| GPU | ~1-3 секунды |

## Масштабирование

Для увеличения производительности запустите несколько воркеров:

```bash
docker-compose up -d --scale ocr-service=3
```

## Логи

```bash
# Просмотр логов
docker-compose logs -f ocr-service

# Логи с фильтрацией
docker-compose logs -f ocr-service | grep "✅"
```

## Структура проекта

```
dev/ocr/
├── app/
│   ├── __init__.py
│   ├── database.py       # Настройки БД и RabbitMQ
│   ├── models.py         # ORM модель Certificate
│   ├── ocr_service.py    # PaddleOCR-VL 1.5
│   ├── rabbitmq.py       # Отправка в llm_tasks
│   └── worker.py         # Основной воркер
├── .env                  # Конфигурация
├── .env.example          # Пример конфигурации
├── Dockerfile
├── requirements.txt
└── README.md
```

## Требования

- Docker, Docker Compose
- PostgreSQL 16+
- RabbitMQ 3+
- 8GB+ RAM (для загрузки модели)
- 10GB+ свободного места (для модели)
