# tests/e2e/test_performance_pipeline.py
import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session

def wait_for_performance_metric(db_engine, portfolio_id, expected_date, timeout=90):
    """
    Polls the database until a performance metric for the specified portfolio and date exists.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        with Session(db_engine) as session:
            query = text("""
                SELECT COUNT(*) FROM daily_performance_metrics
                WHERE portfolio_id = :portfolio_id AND date = :expected_date
            """)
            count = session.execute(query, {"portfolio_id": portfolio_id, "expected_date": expected_date}).scalar()
            if count and count > 0:
                print(f"Validated performance metric exists for {portfolio_id} on {expected_date}")
                return
        time.sleep(2)
    pytest.fail(f"Performance metric for {portfolio_id} on {expected_date} did not appear within {timeout}s.")

@pytest.fixture(scope="module")
def setup_performance_data(clean_db_module, db_engine, api_endpoints):
    """
    A module-scoped fixture to ingest data for a simple two-day performance scenario
    and wait for the backend calculations to complete.
    """
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = "E2E_PERF_PORT_01"
    
    # Day 1: 2025-07-28
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "PERF_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": "PERF_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "PERF", "security_id": "SEC_PERF", "transaction_date": "2025-07-28T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 100, "gross_transaction_amount": 10000, "trade_currency": "USD", "currency": "USD"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": "SEC_PERF", "priceDate": "2025-07-28", "price": 101.0, "currency": "USD"}]})

    # Day 2: 2025-07-29
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": "SEC_PERF", "priceDate": "2025-07-29", "price": 103.0, "currency": "USD"}]})

    # Poll until the metric for the last day is persisted
    wait_for_performance_metric(db_engine, portfolio_id, "2025-07-29")
    
    return {"portfolio_id": portfolio_id, "query_url": api_endpoints["query"]}

def test_performance_e2e_pipeline(setup_performance_data):
    """
    Tests the full pipeline by ingesting data and querying the performance endpoint.
    """
    # ARRANGE
    portfolio_id = setup_performance_data["portfolio_id"]
    query_url = setup_performance_data["query_url"]
    api_url = f"{query_url}/portfolios/{portfolio_id}/performance"
    
    # Day 1 Return: (10100 EOD_MV - 10000 BOD_CF) / 10000 = 1.0%
    # Day 2 Return: (10300 EOD_MV - 10100 BOD_MV) / 10100 = 1.98%
    # Total Linked Return = (1.01 * 1.0198) - 1 = 3.0%
    
    request_payload = {
        "metric_basis": "NET",
        "periods": [
            {
                "type": "EXPLICIT",
                "start_date": "2025-07-28",
                "end_date": "2025-07-29"
            }
        ]
    }
    
    # ACT
    response = requests.post(api_url, json=request_payload)
    
    # ASSERT
    assert response.status_code == 200
    data = response.json()
    
    assert data["portfolio_id"] == portfolio_id
    assert "TOTAL" in data["results"]
    assert pytest.approx(data["results"]["TOTAL"]["returnPct"], abs=1e-2) == 3.0