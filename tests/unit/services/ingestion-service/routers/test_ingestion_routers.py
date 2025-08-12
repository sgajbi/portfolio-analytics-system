# tests/unit/services/ingestion-service/routers/test_ingestion_routers.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

# Import the main FastAPI app and the dependency we need to override
from src.services.ingestion_service.app.main import app
from src.services.ingestion_service.app.services.ingestion_service import get_ingestion_service, IngestionService

@pytest.fixture
def client_with_mock_service():
    """
    Provides a TestClient with the IngestionService dependency replaced by a MagicMock.
    """
    # Use a standard MagicMock since the service methods are now synchronous
    mock_service = MagicMock(spec=IngestionService)
    
    # The dependency override function can be a simple function
    def override_dependency():
        return mock_service

    app.dependency_overrides[get_ingestion_service] = override_dependency
    
    yield TestClient(app), mock_service
    
    del app.dependency_overrides[get_ingestion_service]


def test_ingest_portfolios_endpoint(client_with_mock_service):
    """Tests the POST /ingest/portfolios endpoint."""
    client, mock_service = client_with_mock_service
    mock_service.publish_portfolios.reset_mock()
    payload = { "portfolios": [{"portfolioId": "P1", "baseCurrency": "USD", "openDate": "2025-01-01", "cifId":"c", "status":"s", "riskExposure":"r", "investmentTimeHorizon":"i", "portfolioType":"t", "bookingCenter":"b"}] }
    
    response = client.post("/ingest/portfolios", json=payload)
    
    assert response.status_code == 202
    assert response.json() == {"message": "Successfully queued 1 portfolios for processing."}
    mock_service.publish_portfolios.assert_called_once()

def test_ingest_transactions_endpoint(client_with_mock_service):
    """Tests the POST /ingest/transactions endpoint."""
    client, mock_service = client_with_mock_service
    mock_service.publish_transactions.reset_mock()
    payload = { "transactions": [{"transaction_id": "T1", "portfolio_id": "P1", "instrument_id": "I1", "security_id": "S1", "transaction_date": "2025-08-12T10:00:00Z", "transaction_type": "BUY", "quantity": 1, "price": 1, "gross_transaction_amount": 1, "trade_currency": "USD", "currency": "USD"}] }
    
    response = client.post("/ingest/transactions", json=payload)
    
    assert response.status_code == 202
    mock_service.publish_transactions.assert_called_once()

def test_ingest_instruments_endpoint(client_with_mock_service):
    """Tests the POST /ingest/instruments endpoint."""
    client, mock_service = client_with_mock_service
    mock_service.publish_instruments.reset_mock()
    payload = { "instruments": [{"securityId": "S1", "name": "N1", "isin": "I1", "instrumentCurrency": "USD", "productType": "E"}] }
    
    response = client.post("/ingest/instruments", json=payload)
    
    assert response.status_code == 202
    mock_service.publish_instruments.assert_called_once()

def test_ingest_market_prices_endpoint(client_with_mock_service):
    """Tests the POST /ingest/market-prices endpoint."""
    client, mock_service = client_with_mock_service
    mock_service.publish_market_prices.reset_mock()
    payload = { "market_prices": [{"securityId": "S1", "priceDate": "2025-01-01", "price": 100, "currency": "USD"}] }
    
    response = client.post("/ingest/market-prices", json=payload)
    
    assert response.status_code == 202
    mock_service.publish_market_prices.assert_called_once()

def test_ingest_fx_rates_endpoint(client_with_mock_service):
    """Tests the POST /ingest/fx-rates endpoint."""
    client, mock_service = client_with_mock_service
    mock_service.publish_fx_rates.reset_mock()
    payload = { "fx_rates": [{"fromCurrency": "USD", "toCurrency": "EUR", "rateDate": "2025-01-01", "rate": 0.9}] }
    
    response = client.post("/ingest/fx-rates", json=payload)
    
    assert response.status_code == 202
    mock_service.publish_fx_rates.assert_called_once()