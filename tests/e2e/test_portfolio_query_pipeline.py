import pytest
import requests
import time
from sqlalchemy.orm import Session
from sqlalchemy import text

def wait_for_portfolios_in_db(db_engine, expected_count, timeout=30):
    """Helper function to poll the database until a certain number of portfolios are found."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        with Session(db_engine) as session:
            query = text("SELECT COUNT(*) FROM portfolios")
            count = session.execute(query).scalar_one()
            if count >= expected_count:
                return
        time.sleep(1)
    pytest.fail(f"Expected {expected_count} portfolios in the database, but found {count} after {timeout} seconds.")

@pytest.fixture(scope="module")
def setup_portfolio_data(docker_services, db_engine):
    """A module-scoped fixture to ingest portfolio data once for all tests in this file."""
    host = docker_services.get_service_host("ingestion-service", 8000)
    port = docker_services.get_service_port("ingestion-service", 8000)
    api_url = f"http://{host}:{port}/ingest/portfolios"

    payload = {"portfolios": [
        {
            "portfolioId": "E2E_QUERY_01", "baseCurrency": "USD", "openDate": "2024-01-01",
            "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary",
            "bookingCenter": "Singapore", "cifId": "CIF_100", "status": "Active"
        },
        {
            "portfolioId": "E2E_QUERY_02", "baseCurrency": "CHF", "openDate": "2024-02-01",
            "riskExposure": "Medium", "investmentTimeHorizon": "Medium", "portfolioType": "Advisory",
            "bookingCenter": "Singapore", "cifId": "CIF_100", "status": "Active"
        },
        {
            "portfolioId": "E2E_QUERY_03", "baseCurrency": "EUR", "openDate": "2024-03-01",
            "riskExposure": "Low", "investmentTimeHorizon": "Short", "portfolioType": "Execution-only",
            "bookingCenter": "Zurich", "cifId": "CIF_200", "status": "Closed"
        }
    ]}

    response = requests.post(api_url, json=payload)
    assert response.status_code == 202

    # Wait for the data to be persisted before running tests
    wait_for_portfolios_in_db(db_engine, 3)

    return {
        "query_host": docker_services.get_service_host("query-service", 8001),
        "query_port": docker_services.get_service_port("query-service", 8001)
    }

def test_query_by_portfolio_id(setup_portfolio_data):
    """Tests fetching a single portfolio by its unique ID."""
    env = setup_portfolio_data
    url = f"http://{env['query_host']}:{env['query_port']}/portfolios?portfolio_id=E2E_QUERY_01"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == "E2E_QUERY_01"
    assert data["portfolios"][0]["base_currency"] == "USD"

def test_query_by_cif_id(setup_portfolio_data):
    """Tests fetching all portfolios belonging to a specific client (CIF ID)."""
    env = setup_portfolio_data
    url = f"http://{env['query_host']}:{env['query_port']}/portfolios?cif_id=CIF_100"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) == 2
    portfolio_ids = {p["portfolio_id"] for p in data["portfolios"]}
    assert "E2E_QUERY_01" in portfolio_ids
    assert "E2E_QUERY_02" in portfolio_ids

def test_query_by_booking_center(setup_portfolio_data):
    """Tests fetching all portfolios from a specific booking center."""
    env = setup_portfolio_data
    url = f"http://{env['query_host']}:{env['query_port']}/portfolios?booking_center=Zurich"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) == 1
    assert data["portfolios"][0]["portfolio_id"] == "E2E_QUERY_03"
    assert data["portfolios"][0]["status"] == "Closed"

def test_query_no_filters(setup_portfolio_data):
    """Tests that fetching with no filters returns all portfolios."""
    env = setup_portfolio_data
    url = f"http://{env['query_host']}:{env['query_port']}/portfolios"

    response = requests.get(url)
    assert response.status_code == 200
    data = response.json()

    assert len(data["portfolios"]) >= 3