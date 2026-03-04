"""
LLM Worker - воркер для структурирования текста сертификатов

Архитектура:
1. OCR Worker отправляет задачу в очередь 'llm_tasks' (RabbitMQ)
2. LLM воркер потребляет из 'llm_tasks'
3. Отправляет текст в Ollama для структурирования
4. Сохраняет результат в БД (structured_data)
5. Обновляет статус сертификата на 'completed'
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy.orm import Session

from app.database import (
    sync_engine, sync_session_maker,
    LLM_QUEUE, RABBITMQ_URL, DEBUG, PREFETCH_COUNT
)
from app.models import Certificate, Base
from app.ollama_client import get_ollama_client

logging.basicConfig(
    level=logging.INFO if not DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LLMWorker:
    """Воркер обработки LLM задач"""
    
    def __init__(self):
        self.ollama = get_ollama_client()
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
    
    async def connect(self):
        """Подключение к RabbitMQ и БД"""
        # Инициализация БД
        async with sync_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ БД подключена")
        
        # Подключение к RabbitMQ
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=PREFETCH_COUNT)
        
        # Проверка подключения к Ollama
        await self.ollama.check_connection()
        
        logger.info("✅ RabbitMQ подключен")
    
    async def disconnect(self):
        """Отключение"""
        if self.connection:
            await self.connection.close()
        logger.info("🔌 Отключено")
    
    def save_result(self, certificate_id: str, structured_data: Optional[Dict[str, Any]], success: bool, error: Optional[str] = None):
        """Сохранение результата в БД"""
        with sync_session_maker() as session:
            cert = session.get(Certificate, certificate_id)
            if not cert:
                logger.error(f"Сертификат {certificate_id} не найден")
                return
            
            if success and structured_data:
                cert.structured_data = structured_data
                cert.status = "completed"
                cert.completed_at = datetime.utcnow()
                logger.info(f"✅ Сертификат {certificate_id} обработан")
            else:
                cert.status = "error"
                cert.error_message = error
                cert.completed_at = datetime.utcnow()
                logger.error(f"❌ Ошибка обработки сертификата {certificate_id}: {error}")
            
            session.commit()
    
    async def process_message(self, message: AbstractIncomingMessage):
        """Обработка сообщения из очереди"""
        async with message.process():
            try:
                task_data = message.json()
                certificate_id = task_data.get("certificate_id")
                extracted_text = task_data.get("extracted_text", "")
                
                logger.info(f"🔄 Обработка сертификата {certificate_id}")
                
                if not extracted_text:
                    raise ValueError("Пустой текст для обработки")
                
                # Структурирование через Ollama
                structured_data = await self.ollama.structure_certificate(extracted_text)
                
                if not structured_data:
                    raise ValueError("Не удалось структурировать данные")
                
                logger.info(f"📊 Структурированные данные: {structured_data}")
                
                # Сохранение в БД
                self.save_result(certificate_id, structured_data, success=True)
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки: {e}", exc_info=True)
                task_data = message.json() if message.body else {}
                self.save_result(
                    task_data.get("certificate_id"),
                    None,
                    success=False,
                    error=str(e)
                )
    
    async def run(self):
        """Запуск воркера"""
        await self.connect()
        
        # Объявление очереди LLM задач
        queue = await self.channel.declare_queue(LLM_QUEUE, durable=True)
        logger.info(f"📥 Очередь LLM задач: {LLM_QUEUE}")
        
        # Подписка на очередь
        await queue.consume(self.process_message)
        logger.info("🚀 LLM Worker запущен")
        
        # Ожидание сообщений
        await asyncio.Future()


def main():
    """Точка входа"""
    worker = LLMWorker()
    
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка воркера...")
    finally:
        asyncio.run(worker.disconnect())


if __name__ == "__main__":
    main()
