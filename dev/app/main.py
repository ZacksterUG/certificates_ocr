"""
FastAPI приложение для OCR обработки сертификатов.
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
import uuid
import json
import asyncpg
import aio_pika
import logging
from datetime import datetime

# Загрузка .env
load_dotenv(Path(__file__).parent / ".env")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Глобальные подключения
db_pool: asyncpg.Pool = None
rabbit_connection: aio_pika.Connection = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения."""
    global db_pool, rabbit_connection

    # Startup
    logger.info("🚀 Starting up...")

    # Подключение к PostgreSQL
    db_pool = await asyncpg.create_pool(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "certificates"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASS", "postgres"),
        min_size=2,
        max_size=10,
    )
    logger.info("✅ Connected to PostgreSQL")

    # Подключение к RabbitMQ
    rabbit_connection = await aio_pika.connect(
        host=os.getenv("RABBIT_HOST", "localhost"),
        port=int(os.getenv("RABBIT_PORT", "5672")),
        login=os.getenv("RABBIT_USER", "guest"),
        password=os.getenv("RABBIT_PASS", "guest"),
    )
    logger.info("✅ Connected to RabbitMQ")

    yield

    # Shutdown
    if db_pool:
        await db_pool.close()
        logger.info("👋 PostgreSQL connection closed")

    if rabbit_connection:
        await rabbit_connection.close()
        logger.info("👋 RabbitMQ connection closed")


# Создание приложения
app = FastAPI(
    title="OCR Certificates API",
    description="""
## Сервис обработки сертификатов

Сервис принимает сертификаты/дипломы/грамоты в виде изображений или PDF файлов,
обрабатывает их с помощью OCR и извлекает структурированные данные.

### Архитектура обработки:
1. **Загрузка файла** - пользователь загружает файл через API
2. **OCR обработка** - сервис распознаёт текст из изображения (PaddleOCR-VL)
3. **LLM структурирование** - сервис извлекает данные в JSON формат (Ollama)

### Статусы задач:
- `pending` - ожидает обработки
- `ocr_processing` - OCR обработка
- `ocr_completed` - OCR завершён успешно
- `ocr_error` - ошибка OCR
- `llm_processing` - LLM обработка
- `completed` - полностью обработано
- `error` - ошибка LLM обработки
""",
    version="1.0.0",
    contact={
        "name": "OCR Team",
    },
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)


# ==================== Pydantic Models ====================

class TaskResponse(BaseModel):
    """
    Ответ при успешной отправке задачи.
    """
    id: str = Field(..., description="UUID задачи")
    status: str = Field(..., description="Статус задачи (pending)")
    message: str = Field(..., description="Сообщение о результате")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "pending",
                    "message": "Задача создана и отправлена в очередь"
                }
            ]
        }
    }


class ErrorResponse(BaseModel):
    """
    Ответ при ошибке.
    """
    detail: str = Field(..., description="Описание ошибки")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "detail": "Ошибка при обработке файла: недопустимый формат"
                }
            ]
        }
    }


class SignatoryInfo(BaseModel):
    """
    Информация о подписанте документа.
    """
    position: Optional[str] = Field(None, description="Должность подписанта")
    name: Optional[str] = Field(None, description="ФИО подписанта")
    degree: Optional[str] = Field(None, description="Учёная степень")
    signature_present: Optional[bool] = Field(None, description="Наличие подписи")


class PersonalData(BaseModel):
    """
    Личные данные из сертификата.
    """
    full_name: Optional[str] = Field(None, description="ФИО в именительном падеже")
    full_name_raw: Optional[str] = Field(None, description="ФИО как в документе")
    is_team: Optional[bool] = Field(None, description="Командное ли участие")
    team_name: Optional[str] = Field(None, description="Название команды")
    team_members: Optional[list] = Field(None, description="Участники команды")
    course: Optional[str] = Field(None, description="Курс обучения")
    group: Optional[str] = Field(None, description="Учебная группа")
    university: Optional[str] = Field(None, description="Учебное заведение")
    faculty: Optional[str] = Field(None, description="Факультет")
    educational_level: Optional[str] = Field(None, description="Уровень образования")


class DocumentInfo(BaseModel):
    """
    Информация о документе.
    """
    doc_type: Optional[str] = Field(None, description="Тип документа (диплом/грамота/сертификат)")
    doc_number: Optional[str] = Field(None, description="Номер документа")
    doc_degree: Optional[str] = Field(None, description="Степень диплома")
    issue_date: Optional[str] = Field(None, description="Дата выдачи (YYYY-MM-DD)")
    year: Optional[int] = Field(None, description="Год проведения")
    city: Optional[str] = Field(None, description="Город")
    country: Optional[str] = Field(None, description="Страна")
    language: Optional[str] = Field(None, description="Язык документа (ru/en/mixed)")


class EventInfo(BaseModel):
    """
    Информация о мероприятии.
    """
    event_name: Optional[str] = Field(None, description="Название мероприятия")
    event_type: Optional[str] = Field(None, description="Тип мероприятия")
    event_level: Optional[str] = Field(None, description="Уровень мероприятия")
    edition: Optional[str] = Field(None, description="Номер/версия")
    nomination: Optional[str] = Field(None, description="Номинация")
    section: Optional[str] = Field(None, description="Секция конференции")
    direction: Optional[str] = Field(None, description="Направление/профиль")


class Achievement(BaseModel):
    """
    Информация о достижении.
    """
    has_place: Optional[bool] = Field(None, description="Есть ли призовое место")
    place_number: Optional[int] = Field(None, description="Номер места (1, 2, 3)")
    place_text: Optional[str] = Field(None, description="Текстовое описание места")
    degree: Optional[str] = Field(None, description="Степень диплома")
    prize_name: Optional[str] = Field(None, description="Название приза")
    result_details: Optional[str] = Field(None, description="Конкретные результаты")
    category: Optional[str] = Field(None, description="Категория")
    is_participant_only: Optional[bool] = Field(None, description="Только участие")


class WorkInfo(BaseModel):
    """
    Информация о работе/проекте.
    """
    work_title: Optional[str] = Field(None, description="Название работы")
    work_type: Optional[str] = Field(None, description="Тип работы")
    isbn: Optional[str] = Field(None, description="ISBN")
    scientific_supervisor: Optional[str] = Field(None, description="Научный руководитель")
    supervisor_degree: Optional[str] = Field(None, description="Степень руководителя")


class Organization(BaseModel):
    """
    Организаторы и партнёры.
    """
    primary_org: Optional[str] = Field(None, description="Основной организатор")
    partner_orgs: Optional[list] = Field(None, description="Партнёрские организации")
    sponsors: Optional[list] = Field(None, description="Спонсоры")
    university_org: Optional[str] = Field(None, description="Вуз организатор")


class Metadata(BaseModel):
    """
    Метаданные обработки.
    """
    needs_review: Optional[bool] = Field(None, description="Требуется ли проверка")
    review_reason: Optional[str] = Field(None, description="Причина проверки")
    confidence: Optional[float] = Field(None, description="Уверенность (0.0-1.0)")
    ocr_quality: Optional[str] = Field(None, description="Качество OCR (high/medium/low)")
    ocr_issues: Optional[list] = Field(None, description="Проблемы OCR")
    extraction_notes: Optional[str] = Field(None, description="Дополнительные заметки")


class StructuredData(BaseModel):
    """
    Структурированные данные из сертификата.
    """
    personal_data: Optional[PersonalData] = Field(None, description="Личные данные")
    document_info: Optional[DocumentInfo] = Field(None, description="Информация о документе")
    event_info: Optional[EventInfo] = Field(None, description="Информация о мероприятии")
    achievement: Optional[Achievement] = Field(None, description="Достижения")
    work_info: Optional[WorkInfo] = Field(None, description="Информация о работе")
    organization: Optional[Organization] = Field(None, description="Организации")
    signatories: Optional[list[SignatoryInfo]] = Field(None, description="Подписанты")
    metadata: Optional[Metadata] = Field(None, description="Метаданные")


class TaskStatusResponse(BaseModel):
    """
    Ответ при запросе статуса задачи.
    """
    id: str = Field(..., description="UUID задачи")
    status: str = Field(..., description="Текущий статус задачи")
    error_message: Optional[str] = Field(None, description="Сообщение об ошибке")
    raw_text: Optional[str] = Field(None, description="Распознанный текст (OCR)")
    structured_data: Optional[StructuredData] = Field(None, description="Структурированные данные (LLM)")
    created_at: Optional[str] = Field(None, description="Время создания задачи")
    completed_at: Optional[str] = Field(None, description="Время завершения")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "status": "completed",
                    "error_message": None,
                    "raw_text": "БЛАГОТВОРИТЕЛЬНЫЙ ФОНД...\nДиплом...",
                    "structured_data": {
                        "personal_data": {
                            "full_name": "Иванов Иван Иванович",
                            "university": "ЮУрГУ",
                            "course": "3 курс"
                        },
                        "document_info": {
                            "doc_type": "сертификат",
                            "issue_date": "2017-09-19",
                            "city": "Челябинск"
                        },
                        "event_info": {
                            "event_name": "Distributed Cloud Computing",
                            "event_type": "воркшоп"
                        },
                        "metadata": {
                            "confidence": 0.95,
                            "ocr_quality": "high",
                            "needs_review": False
                        }
                    },
                    "created_at": "2026-03-21T20:00:00",
                    "completed_at": "2026-03-21T20:02:00"
                }
            ]
        }
    }


# ==================== API Endpoints ====================

@app.post(
    "/api/certificates",
    response_model=TaskResponse,
    summary="Загрузить сертификат для обработки",
    description="""
Загружает файл сертификата/диплома/грамоты (изображение или PDF) для обработки.

**Поддерживаемые форматы:**
- JPG/JPEG
- PNG
- BMP
- PDF

**Процесс:**
1. Файл сохраняется в базу данных
2. Создаётся задача со статусом `pending`
3. Задача отправляется в очередь `text_recognition`
4. Возвращается UUID задачи для отслеживания статуса

**Ограничения:**
- Максимальный размер файла: 50MB
""",
    responses={
        201: {
            "description": "Задача успешно создана",
            "model": TaskResponse
        },
        400: {
            "description": "Недопустимый формат или размер файла",
            "model": ErrorResponse
        },
        500: {
            "description": "Внутренняя ошибка сервера",
            "model": ErrorResponse
        }
    },
    status_code=status.HTTP_201_CREATED,
    tags=["certificates"],
)
async def upload_certificate(file: UploadFile = File(..., description="Файл сертификата (JPG, PNG, PDF)")):
    """
    Загружает файл сертификата и создаёт задачу на обработку.

    - **file**: Файл сертификата в формате изображения или PDF

    Возвращает UUID задачи для последующего отслеживания статуса.
    """
    # Валидация типа файла
    allowed_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/bmp",
        "image/tiff",
        "image/webp",
        "application/pdf",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Неподдерживаемый формат файла: {file.content_type}. Поддерживаемые: {', '.join(allowed_types)}"
        )

    # Чтение содержимого файла
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл пустой"
        )

    if len(content) > 50 * 1024 * 1024:  # 50MB
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Размер файла превышает 50MB"
        )

    # Генерация UUID
    task_id = str(uuid.uuid4())

    try:
        # Сохранение в БД
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO certificates (
                    id, image_data, image_filename, image_mime_type,
                    image_size_bytes, status, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                task_id,
                content,
                file.filename,
                file.content_type,
                len(content),
                "pending",
            )

        # Публикация в RabbitMQ
        channel = await rabbit_connection.channel()
        queue = await channel.declare_queue(
            os.getenv("OCR_QUEUE_NAME", "text_recognition"),
            durable=True,
        )
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=f'{{"id": "{task_id}"}}'.encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=os.getenv("OCR_QUEUE_NAME", "text_recognition"),
        )

        logger.info(f"Создана задача {task_id}: {file.filename} ({file.content_type})")

        return TaskResponse(
            id=task_id,
            status="pending",
            message="Задача создана и отправлена в очередь"
        )

    except Exception as e:
        logger.error(f"Ошибка при создании задачи: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при создании задачи: {str(e)}"
        )


@app.get(
    "/api/certificates/{task_id}",
    response_model=TaskStatusResponse,
    summary="Получить статус задачи",
    description="""
Возвращает текущий статус задачи обработки сертификата по её UUID.

**Возможные статусы:**
- `pending` - задача ожидает обработки
- `ocr_processing` - OCR сервис обрабатывает изображение
- `ocr_completed` - OCR завершён успешно, доступен raw_text
- `ocr_error` - ошибка при OCR обработке
- `llm_processing` - LLM сервис структурирует текст
- `completed` - обработка завершена, доступен structured_data
- `error` - ошибка при LLM обработке

**Если статус `completed`:**
- Поле `raw_text` содержит распознанный текст
- Поле `structured_data` содержит структурированные данные в JSON формате

**Если статус `error` или `ocr_error`:**
- Поле `error_message` содержит описание ошибки
""",
    responses={
        200: {
            "description": "Статус задачи успешно получен",
            "model": TaskStatusResponse
        },
        404: {
            "description": "Задача с указанным UUID не найдена",
            "model": ErrorResponse
        }
    },
    tags=["certificates"],
)
async def get_task_status(task_id: str):
    """
    Возвращает статус задачи обработки сертификата.

    - **task_id**: UUID задачи

    Если статус `completed` - возвращает raw_text и structured_data.
    Если статус `error` - возвращает error_message.
    """
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, status, error_message, raw_text, structured_data, created_at, completed_at
                FROM certificates
                WHERE id = $1
                """,
                task_id,
            )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Задача с ID {task_id} не найдена"
            )

        # Парсинг structured_data если это строка
        structured_data = row["structured_data"]
        if isinstance(structured_data, str):
            try:
                structured_data = json.loads(structured_data)
            except (json.JSONDecodeError, TypeError):
                structured_data = None

        return TaskStatusResponse(
            id=str(row["id"]),
            status=row["status"],
            error_message=row["error_message"],
            raw_text=row["raw_text"],
            structured_data=structured_data,
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
            completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении статуса: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка при получении статуса: {str(e)}"
        )


@app.get(
    "/api/health",
    summary="Проверка работоспособности",
    description="Возвращает статус работоспособности сервиса",
    tags=["system"],
)
async def health_check():
    """Проверка работоспособности сервиса."""
    return {
        "status": "healthy",
        "service": "ocr-certificates-api",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
