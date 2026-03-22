"""
Конфигурация OCR сервиса.
"""
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class RabbitConfig:
    """Конфигурация RabbitMQ."""
    host: str
    port: int
    user: str
    password: str
    heartbeat: int


@dataclass
class DatabaseConfig:
    """Конфигурация PostgreSQL."""
    host: str
    port: int
    database: str
    user: str
    password: str


@dataclass
class Config:
    """Конфигурация OCR сервиса."""
    rabbit: RabbitConfig
    database: DatabaseConfig
    
    # Очереди
    ocr_queue_name: str
    llm_queue_name: str
    
    # Модель
    model_path: str
    prompt_ocr: str
    
    # Обработка
    heartbeat_seconds: int
    max_new_tokens: int


def load_config() -> Config:
    """Загружает конфигурацию из .env файла."""
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    return Config(
        rabbit=RabbitConfig(
            host=os.getenv("RABBIT_HOST", "localhost"),
            port=int(os.getenv("RABBIT_PORT", "5672")),
            user=os.getenv("RABBIT_USER", "guest"),
            password=os.getenv("RABBIT_PASS", "guest"),
            heartbeat=int(os.getenv("HEARTBEAT_SECONDS", "600")),
        ),
        database=DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "certificates"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASS", "postgres"),
        ),
        ocr_queue_name=os.getenv("OCR_QUEUE_NAME", "text_recognition"),
        llm_queue_name=os.getenv("LLM_QUEUE_NAME", "llm_json_builder"),
        model_path=os.getenv("MODEL_PATH", "PaddlePaddle/PaddleOCR-VL-1.5"),
        prompt_ocr=os.getenv("PROMPT_OCR", "OCR:"),
        heartbeat_seconds=int(os.getenv("HEARTBEAT_SECONDS", "600")),
        max_new_tokens=int(os.getenv("MAX_NEW_TOKENS", "512")),
    )
