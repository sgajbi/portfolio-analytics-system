# tests/e2e/test_timeseries_pipeline.py
import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import date

def wait_for_portfolio_timeseries_value(db_engine, portfolio_id, expected_date, column_to_check, expected_value, timeout=180):
    """
    Polls the database until a specific column in the portfolio_timeseries table
    matches an expected value for a given date.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        with Session(db_engine) as session:
            query = text(f"SELECT {column_to_check} FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :expected_date")
            result = session.execute(query, {"portfolio_id": portfolio_id, "expected_date": expected_date}).fetchone()
            if result and result[0] == expected_value:
                print(f"Validated {column_to_check} for {portfolio_id} on {expected_date}")
                return
        time.sleep(3)
    pytest.fail(f"Validation for {portfolio_id} on {expected_date} for column {column_to_check} did not succeed within {timeout} seconds.")


@pytest.fixture(scope="module")
def setup_timeseries_data(clean_db_module, db_engine, api_endpoints):
    """
    A module-scoped fixture to clean the DB, ingest all necessary data once,
    and wait for the pipeline to complete by polling for specific, correct values.
    """
    ingestion_url = api_endpoints["ingestion"]

    def post_data(endpoint, payload):
        url = f"{ingestion_url}{endpoint}"
        response = requests.post(url, json=payload)
        assert response.status_code == 202, f"Failed to post to {endpoint}: {response.text}"

    # Ingest all base data
    post_data("/ingest/portfolios", {"portfolios": [{"portfolioId": "E2E_TS_PORT", "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG", "cifId": "TS_CIF", "status": "Active"}]})
    post_data("/ingest/instruments", {"instruments": [
        {"securityId": "SEC_EUR_STOCK", "name": "Euro Stock", "isin": "EU123", "instrumentCurrency": "EUR", "productType": "Equity"},
        {"securityId": "CASH", "name": "US Dollar", "isin": "USD_CASH", "instrumentCurrency": "USD", "productType": "Cash"}
    ]})
    post_data("/ingest/fx-rates", {"fx_rates": [{"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-07-28", "rate": "1.1"}, {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-07-29", "rate": "1.2"}]})

    # --- Day 1 (2025-07-28) ---
    post_data("/ingest/transactions", {"transactions": [{"transaction_id": "TS_BUY_01", "portfolio_id": "E2E_TS_PORT", "instrument_id": "EUR_STOCK", "security_id": "SEC_EUR_STOCK", "transaction_date": "2025-07-28T00:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 50, "gross_transaction_amount": 5000, "trade_currency": "EUR", "currency": "EUR"}]})
    post_data("/ingest/market-prices", {"market_prices": [{"securityId": "SEC_EUR_STOCK", "priceDate": "2025-07-28", "price": 52, "currency": "EUR"}]})
    
    # --- Day 2 (2025-07-29) ---
    post_data("/ingest/transactions", {"transactions": [{"transaction_id": "TS_FEE_01", "portfolio_id": "E2E_TS_PORT", "instrument_id": "CASH", "security_id": "CASH", "transaction_date": "2025-07-29T00:00:00Z", "transaction_type": "FEE", "quantity": 1, "price": 25, "gross_transaction_amount": 25, "trade_currency": "USD", "currency": "USD"}]})
    post_data("/ingest/market-prices", {"market_prices": [
        {"securityId": "SEC_EUR_STOCK", "priceDate": "2025-07-29", "price": 55, "currency": "EUR"},
        {"securityId": "CASH", "priceDate": "2025-07-29", "price": 1, "currency": "USD"}
    ]})
    
    # Poll specifically for Day 1's cashflow to be correct, ensuring it has been processed
    wait_for_portfolio_timeseries_value(
        db_engine, "E2E_TS_PORT", date(2025, 7, 28), "eod_cashflow", Decimal("-5500.0000000000")
    )
    # Poll for the final value of Day 2 to ensure the full pipeline is complete
    wait_for_portfolio_timeseries_value(
        db_engine, "E2E_TS_PORT", date(2025, 7, 29), "eod_market_value", Decimal("6575.0000000000")
    )
    
    return {"db_engine": db_engine}

def test_timeseries_day_1(setup_timeseries_data):
    """Verify the portfolio time series record for the first day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        result = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-28"}).fetchone()

    assert result is not None, "Time series record for day 1 was not found."
    bod_mv, bod_cf, eod_cf, eod_mv, fees = result
    
    assert bod_mv == Decimal("0.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    assert eod_cf == Decimal("-5500.0000000000")
    assert eod_mv == Decimal("5720.0000000000")
    assert fees == Decimal("0.0000000000")

def test_timeseries_day_2(setup_timeseries_data):
    """Verify the portfolio time series record for the second day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        result = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-29"}).fetchone()

    assert result is not None, "Time series record for day 2 was not found."
    bod_mv, bod_cf, eod_cf, eod_mv, fees = result

    assert bod_mv == Decimal("5720.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    assert eod_cf == Decimal("-25.0000000000")
    assert eod_mv == Decimal("6575.0000000000")
    assert fees == Decimal("25.0000000000")

def test_position_timeseries_day_2(setup_timeseries_data):
    """Verify the individual position time series records for the second day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT security_id, eod_market_value, eod_cashflow, quantity, cost FROM position_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        results = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-29"}).fetchall()

    assert len(results) >= 1, "Expected at least one position time series record for day 2"
    
    records = {row[0]: row for row in results}
    
    # Verify the stock position
    stock_pos = records.get("SEC_EUR_STOCK")
    assert stock_pos is not None
    assert stock_pos.eod_market_value == Decimal("5500.0000000000") # 100 * 55 EUR
    assert stock_pos.eod_cashflow == Decimal("0.0000000000")
    assert stock_pos.quantity == Decimal("100.0000000000")
    assert stock_pos.cost == Decimal("50.0000000000") # Original cost per share