# tests/integration/services/ingestion-service/test_ingestion_routers.py
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
import httpx

from src.services.ingestion_service.app.main import app
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock KafkaProducer."""
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    return mock

@pytest_asyncio.fixture
async def async_test_client(mock_kafka_producer: MagicMock):
    """
    Provides an httpx.AsyncClient with the KafkaProducer dependency replaced by a MagicMock.
    """
    def override_get_kafka_producer():
        return mock_kafka_producer

    app.dependency_overrides[get_kafka_producer] = override_get_kafka_producer
    
    # --- THIS IS THE FIX ---
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
    # --- END FIX ---
        yield client
    
    # Clean up the override after the test
    del app.dependency_overrides[get_kafka_producer]


async def test_ingest_portfolios_endpoint(async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock):
    """Tests the POST /ingest/portfolios endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = { "portfolios": [{"portfolioId": "P1", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId":"c", "status":"s", "riskExposure":"r", "investmentTimeHorizon":"i", "portfolioType":"t", "bookingCenter":"b"}] }
    
    response = await async_test_client.post("/ingest/portfolios", json=payload)
    
    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()

async def test_ingest_transactions_endpoint(async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock):
    """Tests the POST /ingest/transactions endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = { "transactions": [{"transaction_id": "T1", "portfolio_id": "P1", "instrument_id": "I1", "security_id": "S1", "transaction_date": "2025-08-12T10:00:00Z", "transaction_type": "BUY", "quantity": 1, "price": 1, "gross_transaction_amount": 1, "trade_currency": "USD", "currency": "USD"}] }
    
    response = await async_test_client.post("/ingest/transactions", json=payload)
    
    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()

async def test_ingest_instruments_endpoint(async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock):
    """Tests the POST /ingest/instruments endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = { "instruments": [{"securityId": "S1", "name": "N1", "isin": "I1", "instrumentCurrency": "USD", "productType": "E"}] }
    
    response = await async_test_client.post("/ingest/instruments", json=payload)
    
    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()

async def test_ingest_market_prices_endpoint(async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock):
    """Tests the POST /ingest/market-prices endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = { "market_prices": [{"securityId": "S1", "priceDate": "2025-01-01", "price": 100, "currency": "USD"}] }
    
    response = await async_test_client.post("/ingest/market-prices", json=payload)
    
    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()

async def test_ingest_fx_rates_endpoint(async_test_client: httpx.AsyncClient, mock_kafka_producer: MagicMock):
    """Tests the POST /ingest/fx-rates endpoint."""
    mock_kafka_producer.publish_message.reset_mock()
    payload = { "fx_rates": [{"fromCurrency": "USD", "toCurrency": "EUR", "rateDate": "2025-01-01", "rate": 0.9}] }
    
    response = await async_test_client.post("/ingest/fx-rates", json=payload)
    
    assert response.status_code == 202
    mock_kafka_producer.publish_message.assert_called_once()