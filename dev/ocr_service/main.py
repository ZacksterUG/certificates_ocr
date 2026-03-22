import os

# Фикс для ошибки OMP: Initializing libiomp5md.dll already initialized
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import asyncio
import json
import logging
import asyncpg
import aio_pika as rabbit_mq
import torch
from transformers import AutoProcessor, AutoModelForImageTextToText
from PIL import Image
from io import BytesIO
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

# Модель и промпт
MODEL_PATH = config.model_path
PROMPT_OCR = config.prompt_ocr



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


async def update_task_status(pool, task_id: str, status: str, raw_text: str = None, error_message: str = None):
    """Обновление статуса задачи после обработки."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            if status == "ocr_completed":
                await conn.execute(
                    """
                    UPDATE certificates
                    SET 
                        status = $1,
                        raw_text = $2,
                        completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $3
                    """,
                    status,
                    raw_text,
                    task_id,
                )
                logger.info(f"✅ Task {task_id} updated: status={status}, raw_text length={len(raw_text)}")
            elif status == "ocr_processing":
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
            elif status == "ocr_error":
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


async def process_image(model, processor, image_bytes: bytes) -> str:
    """Обработка изображения моделью OCR."""
    logger.info("📷 Processing image...")
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    logger.info(f"Image loaded: {image.size}, mode={image.mode}")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": PROMPT_OCR},
            ],
        }
    ]

    logger.info("Applying chat template...")
    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
        images_kwargs={
            "size": {
                "shortest_edge": processor.image_processor.min_pixels,
                "longest_edge": 1280 * 28 * 28
            }
        },
    ).to(model.device)

    logger.info("Generating text...")
    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=512)

    result = processor.decode(generated_ids[0][inputs["input_ids"].shape[-1]:-1])
    logger.info(f"OCR result: {result[:100]}..." if len(result) > 100 else f"OCR result: {result}")
    return result.strip()


async def process_pdf(model, processor, pdf_bytes: bytes) -> str:
    """Обработка PDF (конвертация первого страницы в изображение)."""
    logger.info("📄 Processing PDF...")
    try:
        import pymupdf
        
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        img_data = pix.tobytes("png")
        doc.close()
        
        logger.info(f"PDF converted to image: {pix.width}x{pix.height}")
        return await process_image(model, processor, img_data)
    except ImportError:
        logger.error("❌ PyMuPDF not installed. PDF processing skipped.")
        raise


async def send_to_llm_queue(channel, task_id: str):
    """Отправляет задачу в очередь llm_json_builder для структуризации."""
    try:
        await channel.declare_queue(config.llm_queue_name, durable=True)
        
        message_body = json.dumps({"id": task_id}).encode()
        
        await channel.default_exchange.publish(
            rabbit_mq.Message(
                body=message_body,
                delivery_mode=rabbit_mq.DeliveryMode.PERSISTENT,
            ),
            routing_key=config.llm_queue_name,
        )
        
        logger.info(f"📤 Sent task {task_id} to queue {config.llm_queue_name}")
        return True
    except Exception as e:
        logger.error(f"Failed to send task {task_id} to {config.llm_queue_name}: {e}")
        return False


async def callback(
    message: rabbit_mq.abc.AbstractIncomingMessage,
    model,
    processor,
    db_pool,
    channel,
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
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE certificates
                    SET 
                        status = $1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2
                    """,
                    "ocr_processing",
                    task_id,
                )
        logger.info(f"⏳ Task {task_id} updated: status=ocr_processing")
        
        # Получаем изображение из БД
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT image_data, image_mime_type
                FROM certificates
                WHERE id = $1
                """,
                task_id,
            )
            
            if not row:
                logger.error(f"❌ Task {task_id} not found in database")
                return
            
            image_data = bytes(row["image_data"])
            mime_type = row["image_mime_type"]
            logger.info(f"📂 Loaded from DB: mime_type={mime_type}, size={len(image_data)} bytes")
        
        # Обрабатываем в зависимости от типа
        if "pdf" in mime_type:
            result = await process_pdf(model, processor, image_data)
        else:
            result = await process_image(model, processor, image_data)
        
        # Обновляем статус в БД
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE certificates
                    SET 
                        status = $1,
                        raw_text = $2,
                        completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $3
                    """,
                    "ocr_completed",
                    result,
                    task_id,
                )
        logger.info(f"✅ Task {task_id} updated: status=ocr_completed, raw_text length={len(result)}")
        
        # Отправляем в LLM очередь для структуризации
        await send_to_llm_queue(channel, task_id)
        
        # Ack сообщения после успешной обработки
        await message.ack()
        
    except Exception as e:
        logger.exception(f"❌ Error processing task: {e}")
        # При ошибке записываем status='ocr_error' и error_message
        if task_id:
            try:
                async with db_pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(
                            """
                            UPDATE certificates
                            SET 
                                status = $1,
                                error_message = $2,
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = $3
                            """,
                            "ocr_error",
                            str(e),
                            task_id,
                        )
                logger.info(f"⚠️ Task {task_id} updated: status=ocr_error")
            except Exception as db_error:
                logger.error(f"Failed to update error status: {db_error}")
        
        # Nack сообщения при ошибке (не возвращать в очередь)
        await message.nack(requeue=False)


async def main():
    # Подключение к БД
    logger.info("🔌 Connecting to PostgreSQL...")
    db_pool = await get_db_pool()
    logger.info("✅ Connected to PostgreSQL")
    
    # Загрузка модели
    logger.info(f"🤖 Loading model: {MODEL_PATH}")
    processor = AutoProcessor.from_pretrained(MODEL_PATH)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_PATH,
        torch_dtype=torch.bfloat16,
    ).to(device).eval()

    logger.info(f"✅ Model loaded on {device}")

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
            config.ocr_queue_name,
            durable=True,
        )

        logger.info(f"✅ Connected to RabbitMQ, queue: {config.ocr_queue_name}")

        # Запуск потребителя
        await queue.consume(
            lambda msg: callback(msg, model, processor, db_pool, channel),
            no_ack=False,
        )

        logger.info(f"⏳ Waiting for messages from {config.ocr_queue_name}... Press Ctrl+C to exit.")

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
