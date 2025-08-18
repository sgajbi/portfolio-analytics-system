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
    A module-scoped fixture to ingest data for a multi-day performance scenario
    and wait for the backend pipeline to generate the necessary time-series data.
    """
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = "E2E_ADV_PERF_01"
    security_id = "SEC_ADV_PERF_01"
    
    # --- Ingest Prerequisite Data ---
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "ADV_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": security_id, "name": "Adv Perf Stock", "isin": "ADV123", "instrumentCurrency": "USD", "productType": "Equity"}]})

    # --- Day 1: 2025-03-10 ---
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": "PERF_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "ADV", "security_id": security_id, "transaction_date": "2025-03-10T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 100, "gross_transaction_amount": 10000, "trade_currency": "USD", "currency": "USD"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": "2025-03-10", "price": 102.0, "currency": "USD"}]})

    # --- Day 2: 2025-03-11 ---
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": "2025-03-11", "price": 105.0, "currency": "USD"}]})

    # Poll until the timeseries for the last day is fully generated.
    # EOD MV Day 1 = 100 shares * $102/share = 10200
    # EOD MV Day 2 = 100 shares * $105/share = 10500
    wait_for_portfolio_timeseries_value(
        db_engine, portfolio_id, date(2025, 3, 11), "eod_market_value", Decimal("10500.0000000000")
    )
    
    return {"portfolio_id": portfolio_id, "query_url": api_endpoints["query"]}

def test_advanced_performance_api(setup_performance_data):
    """
    Tests the full pipeline by calling the new on-the-fly performance endpoint
    with a request for multiple, complex period types.
    """
    # ARRANGE
    portfolio_id = setup_performance_data["portfolio_id"]
    query_url = setup_performance_data["query_url"]
    api_url = f"{query_url}/portfolios/{portfolio_id}/performance"
    
    # --- Manual Expected Calculations ---
    # Day 1 (Mar 10) RoR: (EOD_MV:10200 - BOD_MV:0 - BOD_CF:10000) / (BOD_MV:0 + BOD_CF:10000) = 2.0%
    # Day 2 (Mar 11) RoR: (EOD_MV:10500 - BOD_MV:10200) / BOD_MV:10200 = 2.941176%
    # Total Linked Return = ((1 + 0.02) * (1 + 0.02941176)) - 1 = 0.0500... => 5.0%
    
    request_payload = {
        "scope": {
            "as_of_date": "2025-03-11",
            "net_or_gross": "NET"
        },
        "periods": [
            { "name": "Month To Date", "type": "MTD" },
            { 
              "name": "SpecificRange",
              "type": "EXPLICIT",
              "from": "2025-03-10",
              "to": "2025-03-11"
            }
        ],
        "options": { "include_cumulative": True, "include_annualized": False }
    }
    
    # ACT
    response = requests.post(api_url, json=request_payload)
    
    # ASSERT
    assert response.status_code == 200
    data = response.json()
    
    assert data["scope"]["net_or_gross"] == "NET"
    assert "Month To Date" in data["summary"]
    assert "SpecificRange" in data["summary"]
    
    # Both periods cover the same underlying data, so their return should be identical.
    # The engine's more complex logic might produce a slightly different result than simple linking.
    # We will trust the engine's output for the assertion. A value close to 5.0 is expected.
    assert pytest.approx(data["summary"]["Month To Date"]["cumulative_return"], abs=1e-4) == 5.0
    assert pytest.approx(data["summary"]["SpecificRange"]["cumulative_return"], abs=1e-4) == 5.0