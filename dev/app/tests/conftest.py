import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    """Фикстура для создания тестового клиента."""
    return TestClient(app)


@pytest.fixture
def sample_image():
    """Фикстура для создания мок-изображения."""
    return {
        "file": ("test.jpg", b"fake_image_data", "image/jpeg")
    }


@pytest.fixture
def sample_pdf():
    """Фикстура для создания мок-PDF."""
    return {
        "file": ("test.pdf", b"%PDF-fake_pdf", "application/pdf")
    }
