import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Database
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "certificates")

# RabbitMQ
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = os.getenv("RABBITMQ_PORT", "5672")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD", "guest")
OCR_QUEUE = os.getenv("OCR_QUEUE", "ocr_tasks")
LLM_QUEUE = os.getenv("LLM_QUEUE", "llm_tasks")

# PaddleOCR-VL Model
MODEL_PATH = os.getenv("MODEL_PATH", "").strip()  # Локальный путь к модели
MODEL_NAME = os.getenv("MODEL_NAME", "PaddlePaddle/PaddleOCR-VL-1.5")
DEVICE = os.getenv("DEVICE", "cpu")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))

# Worker
PREFETCH_COUNT = int(os.getenv("PREFETCH_COUNT", "1"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# URLs
DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
RABBITMQ_URL = f"amqp://{RABBITMQ_USER}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}:{RABBITMQ_PORT}//"

# Синхронный движок для воркера
sync_engine = create_engine(
    DATABASE_URL,
    echo=DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

sync_session_maker = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)
