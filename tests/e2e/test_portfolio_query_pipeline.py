# tests/e2e/test_portfolio_query_pipeline.py
import pytest
import requests
from sqlalchemy.orm import Session
from sqlalchemy import text

@pytest.fixture(scope="module")
def setup_portfolio_data(clean_db_module, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that ingests a set of portfolios,
    and waits for them to be available via the query API.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]

    payload = {"portfolios": [
        {"portfolioId": "E2E_QUERY_01", "baseCurrency": "USD", "openDate": "2024-01-01", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "Singapore", "cifId": "CIF_100", "status": "Active"},
        {"portfolioId": "E2E_QUERY_02", "baseCurrency": "CHF", "openDate": "2024-02-01", "riskExposure": "Medium", "investmentTimeHorizon": "Medium", "portfolioType": "Advisory", "bookingCenter": "Singapore", "cifId": "CIF_100", "status": "Active"},
        {"portfolioId": "E2E_QUERY_03", "baseCurrency": "EUR", "openDate": "2024-03-01", "riskExposure": "Low", "investmentTimeHorizon": "Short", "portfolioType": "Execution-only", "bookingCenter": "Zurich", "cifId": "CIF_200", "status": "Closed"}
    ]}

    response = requests.post(f"{ingestion_url}/ingest/portfolios", json=payload)
    assert response.status_code == 202

    # Poll to ensure all data is persisted before running tests
    poll_for_data(
        f"{query_url}/portfolios",
        lambda data: data.get("portfolios") and len(data["portfolios"]) >= 3,
        timeout=60
    )

    return {"query_url": query_url}


def test_query_by_portfolio_id(setup_portfolio_data):
    """Tests fetching a single portfolio by its unique ID."""
    query_url = setup_portfolio_data['query_url']
    url = f"{query_url}/portfolios?portfolio_id=E2E_QUERY_01"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == "E2E_QUERY_01"
    assert data["portfolios"][0]["base_currency"] == "USD"

def test_query_by_cif_id(setup_portfolio_data):
    """Tests fetching all portfolios belonging to a specific client (CIF ID)."""
    query_url = setup_portfolio_data['query_url']
    url = f"{query_url}/portfolios?cif_id=CIF_100"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) == 2
    portfolio_ids = {p["portfolio_id"] for p in data["portfolios"]}
    assert "E2E_QUERY_01" in portfolio_ids
    assert "E2E_QUERY_02" in portfolio_ids

def test_query_by_booking_center(setup_portfolio_data):
    """Tests fetching all portfolios from a specific booking center."""
    query_url = setup_portfolio_data['query_url']
    url = f"{query_url}/portfolios?booking_center=Zurich"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == "E2E_QUERY_03"
    assert data["portfolios"][0]["status"] == "Closed"

def test_query_no_filters(setup_portfolio_data):
    """Tests that fetching with no filters returns all portfolios."""
    query_url = setup_portfolio_data['query_url']
    url = f"{query_url}/portfolios"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) >= 3