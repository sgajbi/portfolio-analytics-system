# tests/e2e/test_query_service_api.py
import pytest
import requests
import time
import uuid

# This fixture provides the base URLs for the services under test.
@pytest.fixture(scope="module")
def api_endpoints(docker_services):
    """Provides the URLs for the ingestion and query services."""
    ingestion_host = docker_services.get_service_host("ingestion-service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion-service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"

    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)
    query_url = f"http://{query_host}:{query_port}"
    
    return {"ingestion": ingestion_url, "query": query_url}

@pytest.fixture(scope="function") # <-- SCOPE CHANGED FROM "module" TO "function"
def setup_e2e_data(api_endpoints, clean_db):
    """
    A function-scoped fixture to ingest a consistent set of data for each test.
    """
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = f"E2E_API_TEST_{uuid.uuid4()}"
    
    # Ingest Portfolio
    payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "API_CIF", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}
    requests.post(f"{ingestion_url}/ingest/portfolios", json=payload)

    # Ingest Transactions
    transactions = [
        {"transaction_id": f"{portfolio_id}_T1", "portfolio_id": portfolio_id, "instrument_id": "A", "security_id": "S1", "transaction_date": "2025-08-01", "transaction_type": "BUY", "quantity": 10, "price": 100, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": f"{portfolio_id}_T2", "portfolio_id": portfolio_id, "instrument_id": "B", "security_id": "S2", "transaction_date": "2025-08-05", "transaction_type": "BUY", "quantity": 5, "price": 200, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"}
    ]
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": transactions})
    
    # Wait for data to be processed through the pipeline
    time.sleep(10)

    return {"portfolio_id": portfolio_id, "query_url": api_endpoints["query"]}


def test_transaction_query_default_sort(setup_e2e_data):
    """
    Tests that the default sort order for transactions is by date descending.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f'{setup_e2e_data["query_url"]}/portfolios/{portfolio_id}/transactions'
    
    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["transactions"]) == 2
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T2" # 2025-08-05
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T1" # 2025-08-01

def test_transaction_query_custom_sort(setup_e2e_data):
    """
    Tests sorting transactions by quantity in ascending order.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f'{setup_e2e_data["query_url"]}/portfolios/{portfolio_id}/transactions?sort_by=quantity&sort_order=asc'
    
    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["transactions"]) == 2
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T2" # Quantity 5
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T1" # Quantity 10

def test_query_non_existent_portfolio_returns_empty(setup_e2e_data):
    """
    Tests that querying for a portfolio that does not exist returns an empty list, not an error.
    This is the correct behavior for a GET request on a resource collection.
    """
    url = f'{setup_e2e_data["query_url"]}/portfolios/NON_EXISTENT_PORTFOLIO/transactions'
    
    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()
    
    assert data["total"] == 0
    assert len(data["transactions"]) == 0