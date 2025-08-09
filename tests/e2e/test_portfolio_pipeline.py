import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

def test_portfolio_ingestion_pipeline(docker_services, db_engine, clean_db):
    """
    Tests the full pipeline for portfolio ingestion.
    It ingests a new portfolio and verifies that the record is created
    correctly in the database.
    """
    # 1. Get the API endpoint from the running docker-compose stack
    host = docker_services.get_service_host("ingestion_service", 8000)
    port = docker_services.get_service_port("ingestion_service", 8000)
    api_url = f"http://{host}:{port}/ingest/portfolios"

    # 2. Define a test portfolio payload
    portfolio_id = "E2E_PORT_001"
    payload = {"portfolios": [{
        "portfolioId": portfolio_id,
        "baseCurrency": "USD",
        "openDate": "2024-01-15",
        "riskExposure": "High",
        "investmentTimeHorizon": "Long",
        "portfolioType": "Discretionary",
        "bookingCenter": "New York",
        "cifId": "CIF_9876",
        "status": "Active"
    }]}

    # 3. Post the portfolio to the ingestion service
    response = requests.post(api_url, json=payload)
    assert response.status_code == 202

    # 4. Poll the portfolios table to verify the result
    with Session(db_engine) as session:
        start_time = time.time()
        timeout = 30 # seconds
        while time.time() - start_time < timeout:
            query = text("SELECT portfolio_id, base_currency, status FROM portfolios WHERE portfolio_id = :portfolio_id")
            result = session.execute(query, {"portfolio_id": portfolio_id}).fetchone()
            if result:
                break
            time.sleep(1)
        else:
            pytest.fail(f"Portfolio record for id '{portfolio_id}' not found within {timeout} seconds.")

    # 5. Assert the final state in the database
    db_portfolio_id, db_currency, db_status = result

    assert db_portfolio_id == portfolio_id
    assert db_currency == "USD"
    assert db_status == "Active"