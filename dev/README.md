# Сервис извлечения информации из сертификатов

Система для автоматической обработки сертификатов: OCR распознавание → структурирование LLM → верификация.

## Архитектура

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│   Student   │────▶│   Backend    │────▶│   RabbitMQ  │────▶│ OCR Worker   │
│   (Client)  │     │  (FastAPI)   │     │ ocr_tasks   │     │ (PaddleOCR)  │
└─────────────┘     └──────┬───────┘     └─────────────┘     └──────┬───────┘
                           │                                         │
                           │                                         ▼
                           │                                  ┌──────────────┐
                           │                                  │  PostgreSQL  │
                           │                                  │  (raw_text)  │
                           │                                  └──────┬───────┘
                           │                                         │
                           │                                         ▼
                           │                                  ┌──────────────┐
                           │                                  │   RabbitMQ   │
                           │                                  │  llm_tasks   │
                           │                                  └──────┬───────┘
                           │                                         │
                           ▼                                         ▼
                    ┌─────────────┐                          ┌──────────────┐
                    │ PostgreSQL  │                          │ LLM Worker   │
                    │ (certificate│                          │  (Ollama)    │
                    └─────────────┘                          └──────┬───────┘
                                                                    │
                                                                    ▼
                                                           ┌──────────────┐
                                                           │  PostgreSQL  │
                                                           │ (structured) │
                                                           └──────────────┘
```

## Компоненты

### 1. Backend (API Gateway)

Приём файлов, валидация, создание задач.

**Endpoints:**
```http
POST /api/v1/certificates/upload
GET /api/v1/certificates/{id}/status
GET /api/v1/certificates/{id}/result
```

### 2. OCR Worker (PaddleOCR-VL 1.5)

Распознавание текста из изображений/PDF.

- Потребляет из очереди `ocr_tasks`
- Обновляет `certificates.raw_text`
- Публикует в `llm_tasks`

### 3. LLM Worker (Ollama)

Структурирование текста в JSON.

- Потребляет из очереди `llm_tasks`
- Извлекает: название, организацию, дату, ФИО, тип достижения
- Обновляет `certificates.structured_data`

## Технологический стек

| Компонент       | Технология                     |
|-----------------|--------------------------------|
| Backend         | FastAPI + SQLAlchemy           |
| OCR Worker      | PaddleOCR-VL 1.5               |
| LLM Worker      | Ollama (llama3.2)              |
| Брокер          | RabbitMQ 3.x                   |
| База данных     | PostgreSQL 16                  |
| Кеш             | Redis 7                        |
| Миграции        | Liquibase                      |
| Контейнеризация | Docker Compose                 |

## База данных

### Таблица `certificates`

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | uuid | ID сертификата |
| `image_data` | varchar(500) | Путь к файлу |
| `image_filename` | varchar(255) | Имя файла |
| `image_mime_type` | varchar(50) | MIME-тип |
| `image_size_bytes` | bigint | Размер |
| `raw_text` | text | **Текст из OCR** |
| `ocr_confidence_score` | integer | Точность OCR |
| `ocr_page_count` | integer | Страниц |
| `ocr_processing_time_ms` | integer | Время OCR |
| `structured_data` | jsonb | **Результат LLM** |
| `status` | varchar(50) | pending/ocr_completed/... |
| `error_message` | text | Ошибка |
| `student_id` | varchar(100) | ID студента |
| `sent_to_llm` | boolean | Отправлено в LLM |
| `created_at` | timestamp | Создание |
| `updated_at` | timestamp | Обновление |
| `completed_at` | timestamp | Завершение |

### Статусы

- `pending` — ожидает OCR
- `ocr_processing` — обрабатывается OCR
- `ocr_completed` — OCR готов, отправлено в LLM
- `ocr_error` — ошибка OCR
- `llm_processing` — обрабатывается LLM
- `completed` — готово
- `error` — ошибка

## Очереди RabbitMQ

| Очередь | От кого | Кому | Сообщение |
|---------|---------|------|-----------|
| `ocr_tasks` | Backend | OCR Worker | `{ certificate_id, file_path }` |
| `llm_tasks` | OCR Worker | LLM Worker | `{ certificate_id, extracted_text }` |

## Быстрый старт

```bash
cd dev

# 1. Скачать модель (опционально, для ускорения запуска)
mkdir -p models
git lfs install
git clone https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.5 models/PaddleOCR-VL-1.5

# 2. Запустить всё
docker-compose up -d

# 3. Проверить логи
docker-compose logs -f ocr-service
```

## Миграции БД

Миграции выполняются автоматически при старте через Liquibase.

```bash
# Принудительный запуск миграций
docker-compose run migrations
```

Структура миграций:
```
db/
├── changelog.xml
└── changelog/
    ├── 001-initial-schema.xml
    └── 002-ocr-fields.xml
```

## Пример использования

### Загрузка сертификата

```python
import requests

# Загрузка файла
files = {'file': open('certificate.pdf', 'rb')}
response = requests.post(
    'http://localhost:8000/api/v1/certificates/upload',
    files=files,
    data={'student_id': '12345'}
)
certificate_id = response.json()['certificate_id']
```

### Проверка статуса

```python
response = requests.get(
    f'http://localhost:8000/api/v1/certificates/{certificate_id}/status'
)
print(response.json())
# {"status": "ocr_completed", "raw_text": "..."}
```

### Получение результата

```python
response = requests.get(
    f'http://localhost:8000/api/v1/certificates/{certificate_id}/result'
)
print(response.json())
# {"structured_data": {"event_name": "...", "organization": "..."}}
```

## Структура проекта

```
dev/
├── docker-compose.yaml
├── README.md
├── db/
│   ├── Dockerfile
│   ├── changelog.xml
│   └── changelog/
│       ├── 001-initial-schema.xml
│       └── 002-ocr-llm-fields.xml
├── backend/              # API Gateway
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   └── rabbitmq.py
├── ocr/                  # OCR Worker (PaddleOCR-VL)
│   ├── app/
│   │   ├── worker.py
│   │   ├── ocr_service.py
│   │   ├── models.py
│   │   └── database.py
│   ├── .env
│   ├── Dockerfile
│   └── README.md
├── llm/                  # LLM Worker (Ollama)
│   ├── app/
│   │   ├── worker.py
│   │   ├── ollama_client.py
│   │   ├── models.py
│   │   └── database.py
│   ├── .env
│   ├── Dockerfile
│   └── README.md
└── frontend/             # UI для студентов (опционально)
```

## Переменные окружения

### PostgreSQL
```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=certificates
```

### RabbitMQ
```
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
```

### OCR Worker
```
MODEL_PATH=/app/models/PaddleOCR-VL-1.5
MODEL_NAME=PaddlePaddle/PaddleOCR-VL-1.5
DEVICE=cpu
OCR_QUEUE=ocr_tasks
LLM_QUEUE=llm_tasks
```

### LLM Worker
```
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2
```

## Масштабирование

```bash
# Запуск нескольких OCR воркеров
docker-compose up -d --scale ocr-service=3

# Запуск нескольких LLM воркеров
docker-compose up -d --scale llm-service=2
```

## Мониторинг

```bash
# Логи всех сервисов
docker-compose logs -f

# Статус контейнеров
docker-compose ps

# RabbitMQ Management UI
open http://localhost:15672  # guest/guest

# PostgreSQL
docker-compose exec postgres psql -U postgres -d certificates
```

## Производительность

| Операция | Время |
|----------|-------|
| OCR (CPU, 1 стр.) | 5-15 сек |
| OCR (GPU, 1 стр.) | 1-3 сек |
| LLM структурирование | 2-5 сек |

## Требования

- Docker 24+
- Docker Compose 2.20+
- 8GB+ RAM
- 15GB+ места (для модели OCR)
