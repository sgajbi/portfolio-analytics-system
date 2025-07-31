# services/ingestion-service/tests/conftest.py
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient

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
    mock.publish_message = AsyncMock()
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

    # The 'with' statement handles startup/shutdown events
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    # Clean up the override after the test is done
    app.dependency_overrides = {}