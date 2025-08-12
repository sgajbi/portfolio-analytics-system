# tests/unit/services/ingestion-service/routers/test_ingestion_routers.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.services.ingestion_service.app.main import app
# Import the producer dependency we want to override
from portfolio_common.kafka_utils import get_kafka_producer, KafkaProducer

@pytest.fixture
def client_with_mock_producer():
    """
    Provides a TestClient with the KafkaProducer dependency replaced by a MagicMock.
    """
    mock_producer = MagicMock(spec=KafkaProducer)
    
    def override_dependency():
        return mock_producer

    app.dependency_overrides[get_kafka_producer] = override_dependency
    
    yield TestClient(app), mock_producer
    
    del app.dependency_overrides[get_kafka_producer]


def test_ingest_portfolios_endpoint(client_with_mock_producer):
    """Tests the POST /ingest/portfolios endpoint."""
    client, mock_producer = client_with_mock_producer
    mock_producer.publish_message.reset_mock()
    payload = { "portfolios": [{"portfolioId": "P1", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId":"c", "status":"s", "riskExposure":"r", "investmentTimeHorizon":"i", "portfolioType":"t", "bookingCenter":"b"}] }
    
    response = client.post("/ingest/portfolios", json=payload)
    
    assert response.status_code == 202
    mock_producer.publish_message.assert_called_once()

def test_ingest_transactions_endpoint(client_with_mock_producer):
    """Tests the POST /ingest/transactions endpoint."""
    client, mock_producer = client_with_mock_producer
    mock_producer.publish_message.reset_mock()
    payload = { "transactions": [{"transaction_id": "T1", "portfolio_id": "P1", "instrument_id": "I1", "security_id": "S1", "transaction_date": "2025-08-12T10:00:00Z", "transaction_type": "BUY", "quantity": 1, "price": 1, "gross_transaction_amount": 1, "trade_currency": "USD", "currency": "USD"}] }
    
    response = client.post("/ingest/transactions", json=payload)
    
    assert response.status_code == 202
    mock_producer.publish_message.assert_called_once()

def test_ingest_instruments_endpoint(client_with_mock_producer):
    """Tests the POST /ingest/instruments endpoint."""
    client, mock_producer = client_with_mock_producer
    mock_producer.publish_message.reset_mock()
    payload = { "instruments": [{"securityId": "S1", "name": "N1", "isin": "I1", "instrumentCurrency": "USD", "productType": "E"}] }
    
    response = client.post("/ingest/instruments", json=payload)
    
    assert response.status_code == 202
    mock_producer.publish_message.assert_called_once()

def test_ingest_market_prices_endpoint(client_with_mock_producer):
    """Tests the POST /ingest/market-prices endpoint."""
    client, mock_producer = client_with_mock_producer
    mock_producer.publish_message.reset_mock()
    payload = { "market_prices": [{"securityId": "S1", "priceDate": "2025-01-01", "price": 100, "currency": "USD"}] }
    
    response = client.post("/ingest/market-prices", json=payload)
    
    assert response.status_code == 202
    mock_producer.publish_message.assert_called_once()

def test_ingest_fx_rates_endpoint(client_with_mock_producer):
    """Tests the POST /ingest/fx-rates endpoint."""
    client, mock_producer = client_with_mock_producer
    mock_producer.publish_message.reset_mock()
    payload = { "fx_rates": [{"fromCurrency": "USD", "toCurrency": "EUR", "rateDate": "2025-01-01", "rate": 0.9}] }
    
    response = client.post("/ingest/fx-rates", json=payload)
    
    assert response.status_code == 202
    mock_producer.publish_message.assert_called_once()