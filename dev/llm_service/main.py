import os

# Фикс для ошибки OMP: Initializing libiomp5md.dll already initialized
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import asyncio
import json
import logging
import asyncpg
import aio_pika as rabbit_mq
import httpx
from config import load_config

# Загрузка конфигурации
config = load_config()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Промпт из конфига (если пустой - используется дефолтный)
SYSTEM_PROMPT = config.system_prompt if config.system_prompt else """
Ты — профессиональный экстрактор данных из студенческих сертификатов, грамот и дипломов.
Твоя задача — извлечь ВСЕ доступные поля из текста и вернуть СТРОГО валидный JSON.

### ВАЖНЫЕ ПРАВИЛА:
1. Возвращай ТОЛЬКО JSON без markdown, без пояснений, без ```json
2. Если поле не найдено — укажи null (не пропускай поля!)
3. Исправляй очевидные ошибки OCR (повторы слов, опечатки, разрывы)
4. ФИО приводи к именительному падежу если возможно, тщательно их проверяй
5. Даты приводи к формату YYYY-MM-DD
6. Оценивай уверенность извлечения (0.0-1.0)
7. Определяй язык документа (ru/en/mixed)

### КРИТИЧЕСКИ ВАЖНЫЕ ПОЛЯ:

#### 1. personal_data
- full_name: ФИО в именительном падеже ("Сальков Михаил Сергеевич") (его тщательно проверяй, он должен соответствовать существующим именам)
- full_name_raw: ФИО как в документе ("Салькову Михаилу Сергеевичу")
- is_team: true если награждается команда (ACM ICPC, хоккей, хор и т.д.)
- team_name: название команды ("La squadra", "Политехник", "Deep Vision")
- team_members: массив ФИО участников команды если указаны
- course: курс обучения ("3 курс", "1-го курса", "студент группы АС-322")
- group: учебная группа ("СГ-306", "ЭУ-354", "КТУР-401")
- university: вуз получателя ("ЮУрГУ", "МГУ", "Samara State Technical University")
- faculty: факультет/институт ("Факультет Экономики", "Архитектурно-строительный институт")
- educational_level: бакалавриат|специалитет|магистратура|аспирантура|другое

#### 2. document_info
- doc_type: диплом|грамота|сертификат|свидетельство|благодарность|дипломный лист|удостоверение|другое
- doc_number: номер документа ("NePS-D2e-012", "21 Х002423056")
- doc_degree: I степени|II степени|III степени|Third degree|null
- issue_date: дата выдачи в YYYY-MM-DD
- year: год проведения (число 4 цифры)
- city: город проведения
- country: страна (по умолчанию "Россия" для русских документов)
- language: ru|en|mixed

#### 3. event_info
- event_name: полное название мероприятия
- event_type: конференция|олимпиада|фестиваль|соревнования|конкурс|турнир|смена|форум|чемпионат|другое
- event_level: вузовский|региональный|всероссийский|международный
- edition: номер/версия ("68-я", "X", "VII", "II тур", "4 этап")
- nomination: номинация ("Шрифты", "Уличный танец", "Технические науки")
- section: секция конференции ("Защита информации", "Экономика и управление")
- direction: направление/профиль ("Строительство", "предпринимательства и менеджмента")

#### 4. achievement
- has_place: boolean, есть ли призовое место
- place_number: число (1, 2, 3) или null
- place_text: как написано ("1 место", "І место", "Third degree", "ПЕРВОЕ место")
- degree: степень диплома ("I степени", "II степени", "Third degree")
- prize_name: название приза ("специальный приз «Дебют сезона»", "лучший доклад")
- result_details: конкретные результаты ("230 КГ", "4x400м", "157.53 очк WILKS", "4.34.0", "127,5 KG")
- category: категория ("до 83 КГ", "девушки", "младшие курсы", "JUNIOR", "W/C: 67,5 KG")
- is_participant_only: true если только участие без призового места

#### 5. work_info
- work_title: название работы/проекта/доклада (в кавычках если есть)
- work_type: ВКР|курсовой проект|научная работа|доклад|проект|исследование|статья|другое
- isbn: ISBN если указан ("978-5-906G26-52-3")
- scientific_supervisor: ФИО научного руководителя
- supervisor_degree: учёная степень ("к.э.н.", "д-р ист. наук", "профессор", "к.т.н., доцент")

#### 6. organization
- primary_org: основной организатор ("ЮУрГУ", "Финансовый университет", "Society of Bulgarian Tribologists")
- partner_orgs: массив партнёрских организаций
- sponsors: массив спонсоров ("Яндекс", "СКБ КОНТУР", "МТС", "Райфайзенбанк", "EY")
- university_org: вуз организатор если отличается от primary_org

#### 7. signatories
- Массив объектов с полями:
- position: должность ("Председатель жюри", "Ректор", "Декан", "Научный руководитель центра")
- name: ФИО подписанта
- degree: учёная степень если указана
- signature_present: true если есть подпись/инициалы

#### 8. metadata
- needs_review: true если есть проблемы с извлечением
- review_reason: причина для проверки
- confidence: уверенность извлечения (0.0-1.0)
- ocr_quality: high|medium|low
- ocr_issues: массив проблем OCR (["повторы слов", "разрывы строк", "смешение регистров", "ошибки распознавания"])
- extraction_notes: дополнительные заметки

### ТИПИЧНЫЕ ОШИБКИ OCR ДЛЯ ИСПРАВЛЕНИЯ:
- "олимпияды" → "олимпиады"
- "НАТРАЖДАЕТСЯ" → "НАГРАЖДАЕТСЯ"
- "учасив" → "участие"
- "Гомельск" × 40 раз → удалить повторы
- "специ альный" → "специальный"
- "внеуч ебной" → "внеучебной"
- "амлепике" → "атлетике"
- "мемров" → "метров"
- "областной" × 40 раз → удалить повторы
- "смуденческой" → "студенческой"
- "ъжъэ" (кракозябры) → пропустить

### ПРИМЕРЫ КОМАНДНЫХ СЕРТИФИКАТОВ:
- ACM ICPC: команда + список участников + coach
- Хоккей: команда + список игроков + даты рождения
- Хоры/танцы: коллектив + руководитель + участники

### ОТВЕТ (ТОЛЬКО JSON):
"""


async def get_db_pool():
    """Создание пула подключений к PostgreSQL."""
    return await asyncpg.create_pool(
        host=config.database.host,
        port=config.database.port,
        database=config.database.database,
        user=config.database.user,
        password=config.database.password,
        min_size=1,
        max_size=1,
    )


async def update_task_status(pool, task_id: str, status: str, structured_data: dict = None, error_message: str = None):
    """Обновление статуса задачи после обработки."""
    async with pool.acquire() as conn:
        if status == "completed":
            await conn.execute(
                """
                UPDATE certificates
                SET 
                    status = $1,
                    structured_data = $2,
                    completed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $3
                """,
                status,
                json.dumps(structured_data, ensure_ascii=False),
                task_id,
            )
            logger.info(f"✅ Task {task_id} updated: status={status}")
        elif status == "llm_processing":
            await conn.execute(
                """
                UPDATE certificates
                SET 
                    status = $1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
                """,
                status,
                task_id,
            )
            logger.info(f"⏳ Task {task_id} updated: status={status}")
        elif status == "error":
            await conn.execute(
                """
                UPDATE certificates
                SET 
                    status = $1,
                    error_message = $2,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $3
                """,
                status,
                error_message,
                task_id,
            )
            logger.info(f"⚠️ Task {task_id} updated: status={status}, error={error_message}")


async def extract_json_from_response(text: str) -> dict:
    """Извлекает JSON из ответа LLM (удаляет markdown обёртки)."""
    # Удаляем markdown code blocks если есть
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    
    if text.endswith("```"):
        text = text[:-3]
    
    text = text.strip()
    
    # Пытаемся распарсить JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        # Пытаемся найти JSON в тексте
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            json_str = text[start:end]
            return json.loads(json_str)
        raise


async def call_ollama(raw_text: str) -> dict:
    """Вызов Ollama API для извлечения структурированных данных."""
    url = f"http://{config.ollama.host}:{config.ollama.port}/api/chat"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Извлеки данные из текста:\n\n{raw_text}"},
    ]

    payload = {
        "model": config.ollama.model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": config.ollama.temperature,
        }
    }

    logger.info(f"🤖 Calling Ollama API at {url} with model {config.ollama.model}")

    async with httpx.AsyncClient(timeout=config.ollama.timeout) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        assistant_message = result["message"]["content"]

        logger.info(f"Ollama response: {assistant_message[:200]}...")

        return await extract_json_from_response(assistant_message)


async def callback(
    message: rabbit_mq.abc.AbstractIncomingMessage,
    db_pool,
):
    """Обработчик сообщений из очереди."""
    task_id = None
    try:
        body = json.loads(message.body.decode())
        task_id = body.get("id")
        
        if not task_id:
            logger.error("❌ Task ID not found in message")
            return
        
        logger.info(f"📥 Received task: {task_id}")
        
        # Обновляем статус на processing
        await update_task_status(db_pool, task_id, "llm_processing")
        
        # Получаем raw_text из БД
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT raw_text
                FROM certificates
                WHERE id = $1 AND status = 'llm_processing'
                """,
                task_id,
            )
            
            if not row:
                logger.error(f"❌ Task {task_id} not found or not in ocr_completed status")
                await update_task_status(db_pool, task_id, "llm_error", error_message="Task not found or wrong status")
                return
            
            raw_text = row["raw_text"]
            logger.info(f"📂 Loaded raw_text from DB: {len(raw_text)} chars")
        
        # Вызываем Ollama для извлечения данных
        structured_data = await call_ollama(raw_text)
        # Обновляем статус в БД
        await update_task_status(db_pool, task_id, "completed", structured_data=structured_data)
        # Ack сообщения после успешной обработки
        await message.ack()
        
    except Exception as e:
        logger.exception(f"❌ Error processing task: {e}")
        # При ошибке записываем status='llm_error' и error_message
        if task_id:
            try:
                await update_task_status(db_pool, task_id, "error", error_message=str(e))
            except Exception as db_error:
                logger.error(f"Failed to update error status: {db_error}")
        
        # Nack сообщения при ошибке (не возвращать в очередь)
        await message.nack(requeue=False)


async def main():
    # Подключение к БД
    logger.info("🔌 Connecting to PostgreSQL...")
    db_pool = await get_db_pool()
    logger.info("✅ Connected to PostgreSQL")

    # Подключение к RabbitMQ с увеличенным heartbeat
    logger.info("🔌 Connecting to RabbitMQ...")
    connection = await rabbit_mq.connect(
        host=config.rabbit.host,
        port=config.rabbit.port,
        login=config.rabbit.user,
        password=config.rabbit.password,
        heartbeat=config.rabbit.heartbeat,
    )

    async with connection:
        channel = await connection.channel()

        # Устанавливаем prefetch_count=1 — только одна задача за раз
        await channel.set_qos(prefetch_count=1)

        # Объявляем очередь
        queue = await channel.declare_queue(
            config.llm_queue_name,
            durable=True,
        )

        logger.info(f"✅ Connected to RabbitMQ, queue: {config.llm_queue_name}")

        # Запуск потребителя
        await queue.consume(
            lambda msg: callback(msg, db_pool),
            no_ack=False,
        )

        logger.info(f"⏳ Waiting for messages from {config.llm_queue_name}... Press Ctrl+C to exit.")

        # Бесконечный цикл ожидания
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass
        finally:
            await db_pool.close()
            logger.info("👋 Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
