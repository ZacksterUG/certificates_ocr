"""
OCR Worker - воркер для обработки задач извлечения текста

Архитектура:
1. Бэкенд создаёт запись в certificates со статусом 'pending'
2. Воркер получает задачу из очереди 'ocr_tasks' (только ID сертификата)
3. Обрабатывает файл через PaddleOCR-VL 1.5
4. Обновляет certificates (raw_text, status='ocr_completed')
5. Отправляет в очередь 'llm_tasks'
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import (
    sync_engine, sync_session_maker,
    OCR_QUEUE, RABBITMQ_URL, DEBUG, PREFETCH_COUNT
)
from app.models import Certificate, CertificateStatus, Base
from app.ocr_service import get_ocr_service
from app.rabbitmq import RabbitMQService

logging.basicConfig(
    level=logging.INFO if not DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OCRWorker:
    def __init__(self):
        self.ocr_service = get_ocr_service()
        self.rabbitmq: Optional[RabbitMQService] = None
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
    
    async def connect(self):
        """Подключение к RabbitMQ и БД"""
        async with sync_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ БД подключена")
        
        self.connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=PREFETCH_COUNT)
        
        self.rabbitmq = RabbitMQService()
        await self.rabbitmq.connect(self.channel)
        
        logger.info("✅ RabbitMQ подключен")
    
    async def disconnect(self):
        if self.connection:
            await self.connection.close()
        if self.rabbitmq:
            await self.rabbitmq.disconnect()
        logger.info("🔌 Отключено")
    
    def save_result(self, certificate_id: str, result: Optional[Dict[str, Any]], success: bool, error: Optional[str] = None):
        """Сохранение результата в certificates"""
        with sync_session_maker() as session:
            cert = session.get(Certificate, certificate_id)
            if not cert:
                logger.error(f"Сертификат {certificate_id} не найден")
                return
            
            if success and result:
                cert.raw_text = result["extracted_text"]
                cert.ocr_confidence_score = result["confidence_score"]
                cert.ocr_page_count = result["page_count"]
                cert.ocr_processing_time_ms = result["processing_time_ms"]
                cert.status = CertificateStatus.OCR_COMPLETED.value
                cert.completed_at = datetime.utcnow()
            else:
                cert.status = CertificateStatus.OCR_ERROR.value
                cert.error_message = error
                cert.completed_at = datetime.utcnow()
            
            session.commit()
            logger.info(f"✅ Статус сертификата {certificate_id} обновлён")
    
    async def send_to_llm(self, cert: Certificate):
        """Отправка в LLM очередь"""
        await self.rabbitmq.send_to_llm_queue({
            "certificate_id": str(cert.id),
            "extracted_text": cert.raw_text,
            "confidence_score": cert.ocr_confidence_score,
            "page_count": cert.ocr_page_count,
            "file_name": cert.image_filename,
            "created_at": datetime.utcnow().isoformat(),
        })
        logger.info(f"📤 Сертификат {cert.id} отправлен в LLM очередь")
    
    async def process_message(self, message: AbstractIncomingMessage):
        """Обработка сообщения из очереди"""
        async with message.process():
            try:
                task_data = message.json()
                certificate_id = task_data.get("certificate_id")
                file_path = task_data.get("file_path")
                
                logger.info(f"🔄 Обработка сертификата {certificate_id} ({file_path})")
                
                # Проверка файла
                if not file_path or not Path(file_path).exists():
                    raise FileNotFoundError(f"Файл не найден: {file_path}")
                
                # Обработка через OCR
                result = await self.ocr_service.process_file(str(file_path))
                logger.info(f"✅ OCR завершён ({result['processing_time_ms']}мс)")
                
                # Сохранение в БД
                self.save_result(certificate_id, result, success=True)
                
                # Отправка в LLM очередь
                with sync_session_maker() as session:
                    cert = session.get(Certificate, certificate_id)
                    if cert and cert.status == CertificateStatus.OCR_COMPLETED.value:
                        await self.send_to_llm(cert)
                        cert.sent_to_llm = True
                        session.commit()
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки: {e}", exc_info=True)
                task_data = message.json() if message.body else {}
                self.save_result(task_data.get("certificate_id"), None, success=False, error=str(e))
    
    async def run(self):
        """Запуск воркера"""
        await self.connect()
        
        queue = await self.channel.declare_queue(OCR_QUEUE, durable=True)
        logger.info(f"📥 Очередь OCR задач: {OCR_QUEUE}")
        
        await queue.consume(self.process_message)
        logger.info("🚀 OCR Worker запущен")
        
        await asyncio.Future()


def main():
    worker = OCRWorker()
    try:
        asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("🛑 Остановка воркера...")
    finally:
        asyncio.run(worker.disconnect())


if __name__ == "__main__":
    main()
