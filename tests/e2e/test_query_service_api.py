# tests/e2e/test_query_service_api.py
import pytest
import requests
import time
import uuid

# This fixture provides the base URLs for the services under test.
@pytest.fixture(scope="module")
def api_endpoints(docker_services):
    """Provides the URLs for the ingestion and query services."""
    ingestion_host = docker_services.get_service_host("ingestion_service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion_service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"

    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)
    query_url = f"http://{query_host}:{query_port}"
    
    return {"ingestion": ingestion_url, "query": query_url}

# FIX: Changed scope from "module" to "function" to match clean_db fixture
@pytest.fixture(scope="function")
def setup_e2e_data(api_endpoints, clean_db):
    """
    A function-scoped fixture to ingest a consistent set of data for each test.
    """
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = f"E2E_API_TEST_{uuid.uuid4()}"
    
    # Ingest Portfolio
    payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "API_CIF", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}
    requests.post(f"{ingestion_url}/ingest/portfolios", json=payload)

    # Ingest a diverse set of transactions for filtering and sorting
    transactions = [
        {"transaction_id": f"{portfolio_id}_T1", "portfolio_id": portfolio_id, "instrument_id": "A", "security_id": "S1", "transaction_date": "2025-08-01T10:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 100, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": f"{portfolio_id}_T2", "portfolio_id": portfolio_id, "instrument_id": "B", "security_id": "S2", "transaction_date": "2025-08-05T11:00:00Z", "transaction_type": "BUY", "quantity": 5, "price": 200, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": f"{portfolio_id}_T3", "portfolio_id": portfolio_id, "instrument_id": "A", "security_id": "S1", "transaction_date": "2025-08-03T12:00:00Z", "transaction_type": "SELL", "quantity": 2, "price": 110, "gross_transaction_amount": 220, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": f"{portfolio_id}_T4", "portfolio_id": portfolio_id, "instrument_id": "C", "security_id": "S3", "transaction_date": "2025-08-05T09:00:00Z", "transaction_type": "BUY", "quantity": 25, "price": 50, "gross_transaction_amount": 1250, "trade_currency": "USD", "currency": "USD"}
    ]
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": transactions})
    
    # Wait for data to be processed through the pipeline
    time.sleep(15)

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
    
    assert len(data["transactions"]) == 4
    # Expected order: T2 (Aug 5 11:00), T4 (Aug 5 09:00), T3 (Aug 3), T1 (Aug 1)
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T2"
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T4"
    assert data["transactions"][2]["transaction_id"] == f"{portfolio_id}_T3"
    assert data["transactions"][3]["transaction_id"] == f"{portfolio_id}_T1"

def test_transaction_query_custom_sort(setup_e2e_data):
    """
    Tests sorting transactions by quantity in ascending order.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f'{setup_e2e_data["query_url"]}/portfolios/{portfolio_id}/transactions?sort_by=quantity&sort_order=asc'
    
    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["transactions"]) == 4
    # Expected order by quantity asc: T3 (2), T2 (5), T1 (10), T4 (25)
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T3"
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T2"
    assert data["transactions"][2]["transaction_id"] == f"{portfolio_id}_T1"
    assert data["transactions"][3]["transaction_id"] == f"{portfolio_id}_T4"

def test_transaction_query_filter_by_security_id(setup_e2e_data):
    """
    Tests filtering transactions by a specific security ID.
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f'{setup_e2e_data["query_url"]}/portfolios/{portfolio_id}/transactions?security_id=S1'
    
    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["transactions"]) == 2
    assert data["total"] == 2
    
    # Verify both transactions for S1 are returned
    returned_ids = {t["transaction_id"] for t in data["transactions"]}
    assert f"{portfolio_id}_T1" in returned_ids
    assert f"{portfolio_id}_T3" in returned_ids

def test_transaction_query_filter_and_sort(setup_e2e_data):
    """
    Tests combining a filter (security_id) with custom sorting (quantity asc).
    """
    portfolio_id = setup_e2e_data["portfolio_id"]
    url = f'{setup_e2e_data["query_url"]}/portfolios/{portfolio_id}/transactions?security_id=S1&sort_by=quantity&sort_order=asc'
    
    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["transactions"]) == 2
    # Expected order for S1 by quantity asc: T3 (2), T1 (10)
    assert data["transactions"][0]["transaction_id"] == f"{portfolio_id}_T3"
    assert data["transactions"][1]["transaction_id"] == f"{portfolio_id}_T1"