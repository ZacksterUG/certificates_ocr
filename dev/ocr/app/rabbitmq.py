import json
from datetime import datetime
from typing import Optional, Dict, Any

import aio_pika
from app.database import LLM_QUEUE


class RabbitMQService:
    def __init__(self):
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
        self.llm_queue: Optional[aio_pika.Queue] = None
    
    async def connect(self, channel: aio_pika.Channel):
        self.channel = channel
        self.llm_queue = await self.channel.declare_queue(LLM_QUEUE, durable=True)
        print(f"✅ LLM очередь готова: {LLM_QUEUE}")
    
    async def disconnect(self):
        if self.connection:
            await self.connection.close()
    
    async def send_to_llm_queue(self, task_data: Dict[str, Any]):
        if not self.llm_queue:
            raise RuntimeError("RabbitMQ не подключен")
        
        message_body = json.dumps({
            "certificate_id": str(task_data.get("certificate_id")),
            "extracted_text": task_data.get("extracted_text", ""),
            "confidence_score": task_data.get("confidence_score"),
            "page_count": task_data.get("page_count"),
            "file_name": task_data.get("file_name"),
            "created_at": datetime.utcnow().isoformat(),
        }, ensure_ascii=False)
        
        message = aio_pika.Message(
            body=message_body.encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        
        await self.llm_queue.put(message)
