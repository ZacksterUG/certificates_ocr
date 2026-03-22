# LLM JSON Builder Service

Сервис для структурирования распознанного текста с использованием Ollama (LLM).

## Архитектура

1. Получает задачи из RabbitMQ очереди `llm_json_builder`
2. Загружает `raw_text` из PostgreSQL (таблица `certificates`)
3. Отправляет текст в Ollama API для извлечения структурированных данных
4. Сохраняет результат в `structured_data` (JSONB)

## Структура данных

Сервис извлекает следующие поля:

```json
{
    "student_name": "ФИО студента полностью",
    "course_name": "Название курса/программы",
    "completion_date": "Дата завершения в формате YYYY-MM-DD или null",
    "institution": "Название учебного заведения",
    "certificate_number": "Номер сертификата или null"
}
```

## Запуск

### 1. Установить зависимости

```bash
cd dev/llm_service
pip install -r requirements.txt
```

### 2. Запустить Ollama

```bash
ollama serve
```

### 3. Запустить сервис

```bash
python main.py
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `OLLAMA_HOST` | `localhost` | Хост Ollama API |
| `OLLAMA_PORT` | `11434` | Порт Ollama API |
| `OLLAMA_MODEL` | `llama3.2` | Модель для извлечения данных |

## Статусы задач

- `llm_processing` — задача в обработке
- `llm_completed` — успешно обработано, `structured_data` заполнен
- `llm_error` — ошибка обработки, `error_message` содержит описание

## Логирование

- `📥` — получение задачи
- `⏳` — обновление статуса
- `🤖` — вызов Ollama API
- `✅` — успешное завершение
- `⚠️` — ошибка
