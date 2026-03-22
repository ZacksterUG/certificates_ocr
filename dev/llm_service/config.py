"""
Конфигурация LLM сервиса.
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
class OllamaConfig:
    """Конфигурация Ollama API."""
    host: str
    port: str
    model: str
    temperature: float
    timeout: float


@dataclass
class Config:
    """Конфигурация LLM сервиса."""
    rabbit: RabbitConfig
    database: DatabaseConfig
    ollama: OllamaConfig
    
    # Очередь
    llm_queue_name: str
    
    # Промпт
    system_prompt: str
    
    # Обработка
    heartbeat_seconds: int


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
        ollama=OllamaConfig(
            host=os.getenv("OLLAMA_HOST", "localhost"),
            port=os.getenv("OLLAMA_PORT", "11434"),
            model=os.getenv("OLLAMA_MODEL", "qwen3-coder:480b-cloud"),
            temperature=float(os.getenv("TEMPERATURE", "0.1")),
            timeout=float(os.getenv("REQUEST_TIMEOUT", "120")),
        ),
        llm_queue_name=os.getenv("LLM_QUEUE_NAME", "llm_json_builder"),
        system_prompt=os.getenv("SYSTEM_PROMPT", ""),
        heartbeat_seconds=int(os.getenv("HEARTBEAT_SECONDS", "600")),
    )
