from sqlalchemy import Column, String, Text, Integer, BigInteger, DateTime, ForeignKey, Boolean, func, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
import uuid
import enum

Base = declarative_base()


class CertificateStatus(str, enum.Enum):
    PENDING = "pending"
    OCR_PROCESSING = "ocr_processing"
    OCR_COMPLETED = "ocr_completed"
    OCR_ERROR = "ocr_error"
    LLM_PROCESSING = "llm_processing"
    COMPLETED = "completed"
    ERROR = "error"


class Certificate(Base):
    __tablename__ = "certificates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Исходные данные
    image_data = Column(String(500))  # Путь к файлу
    image_filename = Column(String(255))
    image_mime_type = Column(String(50))
    image_size_bytes = Column(BigInteger)
    
    # Результат OCR
    raw_text = Column(Text, nullable=True)
    ocr_confidence_score = Column(Integer, nullable=True)
    ocr_page_count = Column(Integer, default=1)
    ocr_processing_time_ms = Column(Integer, nullable=True)
    
    # Результат LLM обработки
    structured_data = Column(JSONB, nullable=True)
    
    # Статус и ошибки
    status = Column(String(50), default="pending")
    error_message = Column(Text, nullable=True)
    
    # Данные студента
    student_id = Column(String(100), nullable=True)
    
    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Флаг отправки в LLM очередь
    sent_to_llm = Column(Boolean, default=False, nullable=False)
