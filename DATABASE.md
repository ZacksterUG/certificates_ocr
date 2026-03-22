# База данных: Certificates

## Таблица: certificates

Хранит данные о сертификатах, грамотах и дипломах для OCR обработки.

```mermaid
erDiagram
    certificates {
        uuid id PK "Первичный ключ"
        bytea image_data NOT NULL "Бинарные данные изображения/PDF"
        varchar image_filename NOT NULL "Имя файла (255 символов)"
        varchar image_mime_type NOT NULL "MIME-тип (50 символов)"
        bigint image_size_bytes NOT NULL "Размер файла в байтах"
        text raw_text NULL "Распознанный текст (OCR результат)"
        jsonb structured_data NULL "Структурированные данные (LLM результат)"
        varchar status NOT NULL "Статус обработки"
        text error_message NULL "Сообщение об ошибке"
        varchar student_id NULL "Идентификатор студента"
        timestamptz created_at NOT NULL "Дата создания"
        timestamptz updated_at NOT NULL "Дата обновления"
        timestamptz completed_at NULL "Дата завершения обработки"
    }
```

## Схема таблицы

| Столбец | Тип данных | PK | FK | NULL | Значение по умолчанию | Комментарий |
|---------|------------|----|----|------|----------------------|-------------|
| `id` | uuid | + | − | − | − | Уникальный идентификатор задачи (генерируется клиентом) |
| `image_data` | bytea | − | − | − | − | Бинарные данные изображения или PDF |
| `image_filename` | varchar(255) | − | − | − | − | Оригинальное имя файла |
| `image_mime_type` | varchar(50) | − | − | − | − | MIME-тип (image/jpeg, application/pdf) |
| `image_size_bytes` | bigint | − | − | − | − | Размер файла в байтах |
| `raw_text` | text | − | − | + | − | Распознанный текст после OCR (заполняется после ocr_completed) |
| `structured_data` | jsonb | − | − | + | − | Структурированные данные после LLM (заполняется после completed) |
| `status` | varchar(50) | − | − | − | − | Статус обработки (см. таблицу статусов ниже) |
| `error_message` | text | − | − | + | − | Сообщение об ошибке (заполняется при ocr_error/error) |
| `student_id` | varchar(100) | − | − | + | − | Идентификатор студента (для связи с другими системами) |
| `created_at` | timestamptz | − | − | − | CURRENT_TIMESTAMP | Дата и время создания записи |
| `updated_at` | timestamptz | − | − | − | CURRENT_TIMESTAMP | Дата и время последнего обновления (обновляется триггером) |
| `completed_at` | timestamptz | − | − | + | − | Дата и время завершения обработки (заполняется при completed) |

## Статусы обработки (тип: certificate_status)

Столбец `status` принимает одно из следующих значений:

| Статус | Описание | Когда устанавливается |
|--------|----------|----------------------|
| `pending` | Задача создана и ожидает обработки | При вставке новой записи в таблицу |
| `ocr_processing` | OCR сервис обрабатывает изображение | Когда OCR сервис взял задачу из очереди |
| `ocr_completed` | OCR завершён успешно | После успешного распознавания текста |
| `ocr_error` | Ошибка при OCR обработке | При ошибке в OCR сервисе |
| `llm_processing` | LLM сервис структурирует текст | Когда LLM сервис взял задачу из очереди |
| `completed` | LLM обработка завершена успешно | После успешного структурирования данных |
| `error` | Ошибка при LLM обработке | При ошибке в LLM сервисе |

## Индексы

| Индекс | Столбцы | Тип | Назначение |
|--------|---------|-----|------------|
| `certificates_pkey` | id | PRIMARY KEY (B-tree) | Уникальность и быстрый поиск по ID |
| `idx_certificates_status` | status | B-tree | Фильтрация по статусу |
| `idx_certificates_created_at` | created_at DESC | B-tree | Сортировка по дате создания (новые первыми) |
| `idx_certificates_student_id` | student_id | B-tree | Поиск по студенту |
| `idx_certificates_status_created` | (status, created_at DESC) | Composite B-tree | Эффективная выборка задач по статусу в порядке создания |

## Триггеры

| Триггер | Событие | Назначение |
|---------|---------|------------|
| `update_updated_at` | BEFORE UPDATE | Автоматически обновляет `updated_at` при изменении записи |
