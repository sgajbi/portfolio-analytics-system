# services/ingestion-service/tests/conftest.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient, ASGITransport

from app.main import app
# Correctly import the dependency that FastAPI resolves
from portfolio_common.kafka_utils import KafkaProducer, get_kafka_producer


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """
    A fixture that provides a mock of the KafkaProducer.
    """
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    return mock


@pytest_asyncio.fixture
async def test_client(mock_kafka_producer: MagicMock) -> AsyncClient:
    """
    An async fixture that provides an httpx.AsyncClient for making
    requests to the FastAPI application. It uses dependency overrides
    to replace the real KafkaProducer with our mock producer for the
    duration of the test.
    """
    # FIX: Override the correct base dependency 'get_kafka_producer'
    app.dependency_overrides[get_kafka_producer] = lambda: mock_kafka_producer

    # Use ASGITransport to wrap the FastAPI app for httpx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up the override after the test is done
    app.dependency_overrides = {}