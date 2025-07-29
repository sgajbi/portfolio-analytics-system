import pytest
import requests
import time
from decimal import Decimal

def wait_for_portfolio_timeseries(db_connection, portfolio_id, expected_date, timeout=60):
    """Helper function to poll the database until a portfolio time series record for a specific date is found."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT date FROM portfolio_timeseries WHERE portfolio_id = %s AND date = %s",
                (portfolio_id, expected_date)
            )
            result = cursor.fetchone()
            if result:
                return
        time.sleep(2)
    pytest.fail(f"Portfolio time series for {portfolio_id} on {expected_date} not found within {timeout} seconds.")

@pytest.fixture(scope="module")
def setup_timeseries_data(docker_services, db_connection):
    """A module-scoped fixture to ingest all necessary data for the time series tests."""
    ingestion_host = docker_services.get_service_host("ingestion-service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion-service", 8000)

    # Helper to post data to endpoints
    def post_data(endpoint, payload):
        url = f"http://{ingestion_host}:{ingestion_port}{endpoint}"
        response = requests.post(url, json=payload)
        assert response.status_code == 202

    # Ingest all base data
    post_data("/ingest/portfolios", {"portfolios": [{"portfolioId": "E2E_TS_PORT", "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG", "cifId": "TS_CIF", "status": "Active"}]})
    post_data("/ingest/instruments", {"instruments": [{"securityId": "SEC_EUR_STOCK", "name": "Euro Stock", "isin": "EU123", "instrumentCurrency": "EUR", "productType": "Equity"}]})
    post_data("/ingest/fx-rates", {"fx_rates": [{"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-07-28", "rate": "1.1"}, {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-07-29", "rate": "1.2"}]})

    # --- Day 1 Data ---
    post_data("/ingest/transactions", {"transactions": [{"transaction_id": "TS_BUY_01", "portfolio_id": "E2E_TS_PORT", "security_id": "SEC_EUR_STOCK", "transaction_date": "2025-07-28", "transaction_type": "BUY", "quantity": 100, "price": 50, "gross_transaction_amount": 5000, "currency": "EUR"}]})
    post_data("/ingest/market-prices", {"market_prices": [{"securityId": "SEC_EUR_STOCK", "priceDate": "2025-07-28", "price": 52, "currency": "EUR"}]})

    # --- Day 2 Data ---
    post_data("/ingest/transactions", {"transactions": [{"transaction_id": "TS_FEE_01", "portfolio_id": "E2E_TS_PORT", "transaction_date": "2025-07-29", "transaction_type": "FEE", "quantity": 1, "price": 25, "gross_transaction_amount": 25, "currency": "USD"}]})
    post_data("/ingest/market-prices", {"market_prices": [{"securityId": "SEC_EUR_STOCK", "priceDate": "2025-07-29", "price": 55, "currency": "EUR"}]})

    # Wait for the final day's processing to complete
    wait_for_portfolio_timeseries(db_connection, "E2E_TS_PORT", "2025-07-29")

def test_timeseries_day_1(setup_timeseries_data, db_connection):
    """Verify the portfolio time series record for the first day."""
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = %s AND date = %s",
            ("E2E_TS_PORT", "2025-07-28")
        )
        result = cursor.fetchone()

    bod_mv, bod_cf, eod_cf, eod_mv, fees = result

    # EOD Cashflow = -5000 EUR (BUY) * 1.1 (FX) = -5500 USD
    # EOD Market Value = 100 qty * 52 EUR/share * 1.1 (FX) = 5720 USD
    assert bod_mv == Decimal("0.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    assert eod_cf == Decimal("-5500.0000000000")
    assert eod_mv == Decimal("5720.0000000000")
    assert fees == Decimal("0.0000000000")

def test_timeseries_day_2(setup_timeseries_data, db_connection):
    """Verify the portfolio time series record for the second day."""
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT bod_market_value, bod_cashflow, eod_cashflow, eod_market_value, fees FROM portfolio_timeseries WHERE portfolio_id = %s AND date = %s",
            ("E2E_TS_PORT", "2025-07-29")
        )
        result = cursor.fetchone()

    bod_mv, bod_cf, eod_cf, eod_mv, fees = result

    # BOD Market Value = EOD Market Value of Day 1 = 5720 USD
    # EOD Cashflow = -25 USD (FEE)
    # EOD Market Value = 100 qty * 55 EUR/share * 1.2 (FX) = 6600 USD
    assert bod_mv == Decimal("5720.0000000000")
    assert bod_cf == Decimal("0.0000000000")
    assert eod_cf == Decimal("-25.0000000000")
    assert eod_mv == Decimal("6600.0000000000")
    assert fees == Decimal("25.0000000000")