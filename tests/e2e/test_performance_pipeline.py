# tests/e2e/test_performance_pipeline.py
import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date

def wait_for_portfolio_timeseries_value(db_engine, portfolio_id, expected_date, column_to_check, expected_value_decimal, timeout=120):
    """
    Polls the database until a specific column in the portfolio_timeseries table
    matches an expected value for a given date.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        with Session(db_engine) as session:
            query = text(f"SELECT {column_to_check} FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :expected_date")
            result = session.execute(query, {"portfolio_id": portfolio_id, "expected_date": expected_date}).fetchone()
            if result and result[0] is not None and result[0] == expected_value_decimal:
                print(f"Validated: {column_to_check} for {portfolio_id} on {expected_date} is {result[0]}")
                return
        time.sleep(3)
    pytest.fail(f"Validation for {portfolio_id} on {expected_date} for column {column_to_check} did not succeed within {timeout} seconds.")


@pytest.fixture(scope="module")
def setup_performance_data(clean_db_module, db_engine, api_endpoints):
    """
    A module-scoped fixture to ingest data for a simple two-day performance scenario
    and wait for the backend calculations to complete.
    """
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = "E2E_PERF_PORT_01"
    security_id = "SEC_PERF_01"
    
    # Day 1 Data (2025-07-28)
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "PERF_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": security_id, "name": "Perf Test Stock", "isin": "PERF123", "instrumentCurrency": "USD", "productType": "Equity"}]})
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": "PERF_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "PERF", "security_id": security_id, "transaction_date": "2025-07-28T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 100, "gross_transaction_amount": 10000, "trade_currency": "USD", "currency": "USD"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": "2025-07-28", "price": 101.0, "currency": "USD"}]})

    # Day 2 Data (2025-07-29)
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": "2025-07-29", "price": 103.0, "currency": "USD"}]})

    # Poll until the timeseries for the last day is fully generated.
    # EOD MV Day 2 = 100 shares * $103/share = 10300
    wait_for_portfolio_timeseries_value(
        db_engine, portfolio_id, date(2025, 7, 29), "eod_market_value", Decimal("10300.0000000000")
    )
    
    return {"portfolio_id": portfolio_id, "query_url": api_endpoints["query"]}

def test_performance_e2e_pipeline(setup_performance_data):
    """
    Tests the full pipeline by ingesting data and querying the new on-the-fly
    performance endpoint.
    """
    # ARRANGE
    portfolio_id = setup_performance_data["portfolio_id"]
    query_url = setup_performance_data["query_url"]
    api_url = f"{query_url}/portfolios/{portfolio_id}/performance"
    
    # --- Manual Calculation ---
    # Day 1 RoR (NET): (EOD_MV:10100 - BOD_MV:0 - BOD_CF:10000) / (BOD_MV:0 + BOD_CF:10000) = 100 / 100000 = 1.0%
    # Day 2 RoR (NET): (EOD_MV:10300 - BOD_MV:10100) / (BOD_MV:10100) = 200 / 10100 = 1.980198%
    # Total Linked Return = ((1 + 0.01) * (1 + 0.01980198)) - 1 = 3.00%
    
    request_payload = {
        "metric_basis": "NET",
        "periods": [
            {
                "name": "CustomPeriod",
                "period": {
                    "start_date": "2025-07-28",
                    "end_date": "2025-07-29"
                }
            }
        ]
    }
    
    # ACT
    response = requests.post(api_url, json=request_payload)
    
    # ASSERT
    assert response.status_code == 200
    data = response.json()
    
    assert data["portfolio_id"] == portfolio_id
    assert "CustomPeriod" in data["results"]
    assert pytest.approx(data["results"]["CustomPeriod"]["returnPct"], abs=1e-4) == 3.0000