"""
Тесты для OCR Certificates API.
"""
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
import main


class AsyncContextManagerMock:
    """Мок для async context manager."""
    def __init__(self, return_value=None):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, *args):
        pass


# Создаём моки
mock_db_pool = MagicMock()
mock_rabbit_connection = MagicMock()

# Патчим lifespan чтобы не подключаться к реальным сервисам
original_lifespan = main.lifespan

async def mock_lifespan(app):
    main.db_pool = mock_db_pool
    main.rabbit_connection = mock_rabbit_connection
    yield

# Заменяем lifespan
main.app.router.lifespan_context = mock_lifespan

# Заменяем глобальные переменные
main.db_pool = mock_db_pool
main.rabbit_connection = mock_rabbit_connection


client = TestClient(main.app)


@pytest.fixture(autouse=True)
def setup_mocks():
    """Настройка моков для каждого теста."""
    # Мок для БД connection
    mock_conn = AsyncMock()

    # Мок для pool.acquire() как async context manager
    mock_db_pool.acquire.return_value = AsyncContextManagerMock(mock_conn)

    # Мок для RabbitMQ
    mock_channel = MagicMock()
    mock_queue = MagicMock()
    mock_rabbit_connection.channel = AsyncMock(return_value=mock_channel)
    mock_channel.declare_queue = AsyncMock(return_value=mock_queue)
    mock_channel.default_exchange.publish = AsyncMock()

    yield {
        "db_pool": mock_db_pool,
        "rabbit_connection": mock_rabbit_connection,
        "db_conn": mock_conn,
    }


class TestUploadCertificate:
    """Тесты для POST /api/certificates."""

    def test_upload_jpg_success(self, setup_mocks):
        """Успешная загрузка JPG файла."""
        file_content = b"fake_image_data"

        response = client.post(
            "/api/certificates",
            files={"file": ("test.jpg", file_content, "image/jpeg")},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"
        assert "message" in data

        setup_mocks["db_conn"].execute.assert_called_once()
        setup_mocks["rabbit_connection"].channel.assert_called_once()

    def test_upload_png_success(self, setup_mocks):
        """Успешная загрузка PNG файла."""
        file_content = b"fake_png_data"

        response = client.post(
            "/api/certificates",
            files={"file": ("test.png", file_content, "image/png")},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"

    def test_upload_pdf_success(self, setup_mocks):
        """Успешная загрузка PDF файла."""
        file_content = b"%PDF-fake_pdf_data"

        response = client.post(
            "/api/certificates",
            files={"file": ("test.pdf", file_content, "application/pdf")},
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["status"] == "pending"

    def test_upload_invalid_format(self):
        """Загрузка неподдерживаемого формата."""
        file_content = b"some_text_file"

        response = client.post(
            "/api/certificates",
            files={"file": ("test.txt", file_content, "text/plain")},
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_upload_empty_file(self):
        """Загрузка пустого файла."""
        file_content = b""

        response = client.post(
            "/api/certificates",
            files={"file": ("empty.jpg", file_content, "image/jpeg")},
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_upload_missing_file(self):
        """Отправка запроса без файла."""
        response = client.post("/api/certificates")

        assert response.status_code == 422


class TestGetTaskStatus:
    """Тесты для GET /api/certificates/{task_id}."""

    def test_get_status_success(self, setup_mocks):
        """Получение статуса существующей задачи."""
        task_id = str(uuid.uuid4())

        mock_row = {
            "id": task_id,
            "status": "completed",
            "error_message": None,
            "raw_text": "Распознанный текст",
            "structured_data": {"personal_data": {"full_name": "Иванов Иван"}},
            "created_at": None,
            "completed_at": None,
        }
        setup_mocks["db_conn"].fetchrow.return_value = mock_row

        response = client.get(f"/api/certificates/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["status"] == "completed"

    def test_get_status_not_found(self, setup_mocks):
        """Получение статуса несуществующей задачи."""
        setup_mocks["db_conn"].fetchrow.return_value = None

        response = client.get("/api/certificates/non-existent-id")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


class TestHealthCheck:
    """Тесты для GET /api/health."""

    def test_health_check(self):
        """Проверка работоспособности."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestOpenAPI:
    """Тесты для OpenAPI документации."""

    def test_openapi_json_available(self):
        """OpenAPI схема должна быть доступна."""
        response = client.get("/api/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_docs_endpoint_available(self):
        """Swagger UI должен быть доступен."""
        response = client.get("/api/docs")

        assert response.status_code == 200

    def test_redoc_endpoint_available(self):
        """ReDoc должен быть доступен."""
        response = client.get("/api/redoc")

        assert response.status_code == 200
