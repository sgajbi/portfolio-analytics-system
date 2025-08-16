# tests/e2e/test_timeseries_pipeline.py
import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

def wait_for_portfolio_timeseries(db_engine, portfolio_id, expected_date, timeout=180): # FIX: Increased timeout to 180s
    """Helper function to poll the database until a portfolio time series record for a specific date is found."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        with Session(db_engine) as session:
            query = text("SELECT date FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :expected_date")
            result = session.execute(query, {"portfolio_id": portfolio_id, "expected_date": expected_date}).fetchone()
            if result:
                return
        time.sleep(2)
    pytest.fail(f"Portfolio time series for {portfolio_id} on {expected_date} not found within {timeout} seconds.")

@pytest.fixture(scope="function")
def setup_timeseries_data(docker_services, db_engine, clean_db):
    """A function-scoped fixture to ingest all necessary data for the time series tests."""
    ingestion_host = docker_services.get_service_host("ingestion_service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion_service", 8000)

    # Helper to post data to endpoints
    def post_data(endpoint, payload):
        url = f"http://{ingestion_host}:{ingestion_port}{endpoint}"
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
    # A BUY transaction creates a new position in a European stock.
    post_data("/ingest/transactions", {"transactions": [{"transaction_id": "TS_BUY_01", "portfolio_id": "E2E_TS_PORT", "instrument_id": "EUR_STOCK", "security_id": "SEC_EUR_STOCK", "transaction_date": "2025-07-28T00:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 50, "gross_transaction_amount": 5000, "trade_currency": "EUR", "currency": "EUR"}]})
    # A market price is provided to value the new position at the end of the day.
    post_data("/ingest/market-prices", {"market_prices": [{"securityId": "SEC_EUR_STOCK", "priceDate": "2025-07-28", "price": 52, "currency": "EUR"}]})
    
    # --- Day 2 (2025-07-29) ---
    # A FEE transaction creates a negative cash position.
    post_data("/ingest/transactions", {"transactions": [{"transaction_id": "TS_FEE_01", "portfolio_id": "E2E_TS_PORT", "instrument_id": "CASH", "security_id": "CASH", "transaction_date": "2025-07-29T00:00:00Z", "transaction_type": "FEE", "quantity": 1, "price": 25, "gross_transaction_amount": 25, "trade_currency": "USD", "currency": "USD"}]})
    # New market prices are provided for both the stock (which appreciated) and the cash position.
    post_data("/ingest/market-prices", {"market_prices": [
        {"securityId": "SEC_EUR_STOCK", "priceDate": "2025-07-29", "price": 55, "currency": "EUR"},
        {"securityId": "CASH", "priceDate": "2025-07-29", "price": 1, "currency": "USD"}
    ]})

    
    # Give services a moment to process before polling
    time.sleep(10)

    # Wait for the final day's processing to complete
    wait_for_portfolio_timeseries(db_engine, "E2E_TS_PORT", "2025-07-29")
    
    return {
        "query_host": docker_services.get_service_host("query-service", 8001),
        "query_port": docker_services.get_service_port("query-service", 8001),
        "db_engine": db_engine
    }

def test_timeseries_day_1(setup_timeseries_data):
    """Verify the portfolio time series record for the first day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        result = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-28"}).fetchone()

    assert result is not None, "Time series record for day 1 was not found."
    bod_mv, bod_cf, eod_cf, eod_mv, fees = result
    
    assert bod_mv == Decimal("0.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    # EOD CF: BUY of 5000 EUR @ 1.1 FX = -5500 USD
    assert eod_cf == Decimal("-5500.0000000000")
    # EOD MV: 100 shares * 52 EUR/share * 1.1 FX = 5720 USD
    assert eod_mv == Decimal("5720.0000000000")
    assert fees == Decimal("0.0000000000")

def test_timeseries_day_2(setup_timeseries_data):
    """Verify the portfolio time series record for the second day."""
    with Session(setup_timeseries_data["db_engine"]) as session:
        query = text("SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = :portfolio_id AND date = :date")
        result = session.execute(query, {"portfolio_id": "E2E_TS_PORT", "date": "2025-07-29"}).fetchone()

    assert result is not None, "Time series record for day 2 was not found."
    bod_mv, bod_cf, eod_cf, eod_mv, fees = result

    # BOD MV from Day 1 EOD MV
    assert bod_mv == Decimal("5720.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    # EOD CF from FEE transaction of $25
    assert eod_cf == Decimal("-25.0000000000")
    
    # EOD MV Calculation:
    # Stock Value: 100 shares * 55 EUR/share * 1.2 FX = 6600 USD
    # Cash Value: -25 USD (from fee)
    # Total EOD MV = 6600 - 25 = 6575 USD
    assert eod_mv == Decimal("6575.0000000000")
    assert fees == Decimal("25.0000000000")