# LLM Worker (Ollama)

Воркер для структурирования текста сертификатов с использованием LLM (Ollama).

## Архитектура

```
┌──────────────┐      ┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│ OCR Worker   │─────▶│   RabbitMQ  │─────▶│ LLM Worker  │─────▶│  PostgreSQL  │
│              │      │ llm_tasks   │      │  (Ollama)   │      │  structured  │
└──────────────┘      └─────────────┘      └──────────────┘      └──────────────┘
```

## Функции

- Потребляет задачи из очереди `llm_tasks`
- Отправляет текст в Ollama для структурирования
- Извлекает: название, организацию, дату, ФИО, тип достижения
- Сохраняет результат в `certificates.structured_data`
- Обновляет статус на `completed`

## Структура данных

### Входное сообщение (llm_tasks)

```json
{
  "certificate_id": "uuid",
  "extracted_text": "South Ural State University\nCertificate...",
  "confidence_score": 92,
  "page_count": 1,
  "file_name": "certificate.pdf"
}
```

### Выходные данные (structured_data)

```json
{
  "event_name": "Всероссийская олимпиада по программированию",
  "organization": "Южно-Уральский государственный университет",
  "issue_date": "2024-05-15",
  "recipient_name": "Иванов Иван Иванович",
  "achievement_type": "olympiad"
}
```

### Типы достижений

- `olympiad` — олимпиада
- `course` — курс/обучение
- `conference` — конференция
- `workshop` — воркшоп/мастер-класс
- `competition` — конкурс/соревнование
- `other` — другое

## Запуск

```bash
cd dev
docker-compose up -d llm-service
```

## Конфигурация (.env)

```bash
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=certificates

# RabbitMQ
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
LLM_QUEUE=llm_tasks

# Ollama
OLLAMA_HOST=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.2
OLLAMA_TIMEOUT=120

# Worker
PREFETCH_COUNT=1
DEBUG=false
```

## Подключение к локальному Ollama

### Windows

1. Установите Ollama: https://ollama.com
2. Скачайте модель:
   ```bash
   ollama pull llama3.2
   ```
3. Разрешите подключения из Docker:
   ```powershell
   # В PowerShell от администратора
   netsh advfirewall firewall add rule name="Ollama" dir=in action=allow protocol=TCP localport=11434
   ```

### Linux

```bash
ollama pull llama3.2
ollama serve --host 0.0.0.0
```

## Проверка работы

```bash
# Логи воркера
docker-compose logs -f llm-service

# Проверка подключения к Ollama
curl http://localhost:11434/api/tags
```

## Производительность

| Модель | Время обработки | RAM |
|--------|----------------|-----|
| llama3.2 | 2-5 сек | 2GB |
| llama3.1:8b | 3-7 сек | 4GB |
| mistral | 2-5 сек | 2GB |
