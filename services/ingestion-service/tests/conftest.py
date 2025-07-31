# services/ingestion-service/tests/conftest.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient, ASGITransport

# The following imports assume that the tests are run from the project root,
# and the `pythonpath` in pyproject.toml is correctly configured.
from app.main import app, get_producer_dependency
from portfolio_common.kafka_utils import KafkaProducer


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """
    A fixture that provides a mock of the KafkaProducer.
    The publish_message method is replaced with an AsyncMock to allow
    for awaiting in tests and to track calls.
    """
    mock = MagicMock(spec=KafkaProducer)
    # The actual method is not async, so we use a standard MagicMock for the method
    # The `await` was in the test, which was incorrect. The publish method is fire-and-forget.
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
    # Override the dependency with our mock
    app.dependency_overrides[get_producer_dependency] = lambda: mock_kafka_producer

    # Use ASGITransport to wrap the FastAPI app for httpx
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up the override after the test is done
    app.dependency_overrides = {}