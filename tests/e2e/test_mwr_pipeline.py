# tests/e2e/test_mwr_pipeline.py
import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date, timedelta

# This helper is defined in the root conftest.py
from tests.conftest import poll_db_until

@pytest.fixture(scope="module")
def setup_mwr_data(clean_db_module, db_engine, api_endpoints, poll_db_until):
    """
    A module-scoped fixture to ingest data for an MWR scenario and wait for the
    backend pipeline to generate the necessary time-series data.
    """
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = "E2E_MWR_PERF_01"
    
    # --- Ingest Prerequisite Data ---
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "MWR_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": "CASH_USD", "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash"}]})

    # --- Ingest Sequentially to Avoid Incorrect Recalculation Triggers ---

    # Day 1 (2025-01-01): Set business date, then ingest transaction and price.
    requests.post(f"{ingestion_url}/ingest/business-dates", json={"business_dates": [{"businessDate": "2025-01-01"}]})
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": "MWR_DEPOSIT_01", "portfolio_id": portfolio_id, "instrument_id": "CASH", "security_id": "CASH_USD", "transaction_date": "2025-01-01T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000, "price": 1, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": "CASH_USD", "priceDate": "2025-01-01", "price": 1.0, "currency": "USD"}]})

    # Day 15 (2025-01-15): Set business date, then ingest transaction.
    requests.post(f"{ingestion_url}/ingest/business-dates", json={"business_dates": [{"businessDate": "2025-01-15"}]})
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": "MWR_DEPOSIT_02", "portfolio_id": portfolio_id, "instrument_id": "CASH", "security_id": "CASH_USD", "transaction_date": "2025-01-15T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 200, "price": 1, "gross_transaction_amount": 200, "trade_currency": "USD", "currency": "USD"}]})
    
    # Day 31 (2025-01-31): Set business date, then ingest final price.
    requests.post(f"{ingestion_url}/ingest/business-dates", json={"business_dates": [{"businessDate": "2025-01-31"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": "CASH_USD", "priceDate": "2025-01-31", "price": 1.04166667, "currency": "USD"}]})

    # Now that transactions are processed, ingest the remaining business dates
    # to trigger the schedulers to fill in the daily time series gaps correctly.
    all_dates = []
    current_date = date(2025, 1, 1)
    while current_date <= date(2025, 1, 31):
        all_dates.append({"businessDate": current_date.isoformat()})
        current_date += timedelta(days=1)
    requests.post(f"{ingestion_url}/ingest/business-dates", json={"business_dates": all_dates})

    # Poll until the timeseries for the last day is fully generated.
    poll_db_until(
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": portfolio_id, "date": "2025-01-31"},
        validation_func=lambda r: r is not None,
        timeout=90,
        fail_message="Pipeline did not generate portfolio_timeseries for the final day."
    )
    
    return {"portfolio_id": portfolio_id, "query_url": api_endpoints["query"]}

def test_mwr_api_calculates_correctly(setup_mwr_data):
    """
    Tests the full MWR pipeline by calling the new endpoint and verifying the result.
    The test scenario is:
    - Jan 1: Begin MV = 1000
    - Jan 15: Contribution = 200
    - Jan 31: End MV = 1250
    """
    # ARRANGE
    portfolio_id = setup_mwr_data["portfolio_id"]
    query_url = setup_mwr_data["query_url"]
    api_url = f"{query_url}/portfolios/{portfolio_id}/performance/mwr"
    
    request_payload = {
        "scope": { "as_of_date": "2025-01-31" },
        "periods": [
            { "type": "EXPLICIT", "name": "TestPeriod", "from": "2025-01-01", "to": "2025-01-31" }
        ],
        "options": { "annualize": True }
    }
    
    # ACT
    response = requests.post(api_url, json=request_payload)
    
    # ASSERT
    assert response.status_code == 200
    data = response.json()
    
    assert "TestPeriod" in data["summary"]
    result = data["summary"]["TestPeriod"]

    # Assert attributes are correct
    attrs = result["attributes"]
    assert Decimal(attrs["begin_market_value"]) == Decimal("1000")
    assert Decimal(attrs["end_market_value"]).quantize(Decimal("0.01")) == Decimal("1250.00")
    assert Decimal(attrs["external_contributions"]) == Decimal("1200") # 1000 deposit + 200 deposit
    assert Decimal(attrs["external_withdrawals"]) == Decimal("0")
    assert attrs["cashflow_count"] == 2

    # Assert MWR calculation is correct
    # The annualized IRR for this cashflow series is ~58.26%
    assert result["mwr"] is not None
    assert pytest.approx(result["mwr"], abs=1e-4) == 0.5826
    
    # Annualized MWR should be null for a period < 1 year
    assert result["mwr_annualized"] is None