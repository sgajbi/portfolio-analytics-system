# tests/e2e/test_full_workflow.py
import pytest
import requests
import time
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date
from decimal import Decimal

# Define constants for the workflow test
PORTFOLIO_ID = "E2E_WORKFLOW_01"
BASE_CURRENCY = "USD"
FOREIGN_CURRENCY = "EUR"

CASH_USD_ID = "CASH_USD"
CASH_EUR_ID = "CASH_EUR"
AAPL_ID = "SEC_AAPL_E2E"
IBM_ID = "SEC_IBM_E2E"

DAY_1 = "2025-08-19"
DEPOSIT_TXN_ID = "TXN_DAY1_DEPOSIT_01"

@pytest.fixture(scope="module")
def setup_and_verify_day1_state(clean_db_module, api_endpoints, poll_for_data, db_engine):
    """
    A module-scoped fixture that performs the entire Day 1 setup and waits
    for the final portfolio timeseries to be fully calculated and available in the DB.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]

    # --- 1. Ingest Portfolio and verify ---
    portfolio_payload = {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": BASE_CURRENCY, "openDate": "2025-01-01", "cifId": "WF_CIF_01", "status": "ACTIVE", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG"}]}
    requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload)
    poll_for_data(
        f"{query_url}/portfolios/{PORTFOLIO_ID}",
        lambda data: data and data.get("portfolio_id") == PORTFOLIO_ID,
        timeout=60
    )

    # --- 2. Ingest Instruments and verify ---
    instruments_payload = {"instruments": [{"securityId": CASH_USD_ID, "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash"}, {"securityId": CASH_EUR_ID, "name": "Euro", "isin": "CASH_EUR_ISIN", "instrumentCurrency": "EUR", "productType": "Cash"}, {"securityId": AAPL_ID, "name": "Apple Inc.", "isin": "US0378331005", "instrumentCurrency": "USD", "productType": "Equity"}, {"securityId": IBM_ID, "name": "IBM Corp.", "isin": "US4592001014", "instrumentCurrency": "USD", "productType": "Equity"}]}
    requests.post(f"{ingestion_url}/ingest/instruments", json=instruments_payload)
    poll_for_data(
        f"{query_url}/instruments?security_id={IBM_ID}",
        lambda data: data and data.get("instruments"),
        timeout=60
    )

    # --- 3. Ingest Prices and verify ---
    prices_payload = {"market_prices": [{"securityId": CASH_USD_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "USD"}, {"securityId": CASH_EUR_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "EUR"}, {"securityId": AAPL_ID, "priceDate": "2025-08-18", "price": 175.0, "currency": "USD"}, {"securityId": IBM_ID, "priceDate": "2025-08-18", "price": 150.0, "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/market-prices", json=prices_payload)
    poll_for_data(
        f"{query_url}/prices?security_id={IBM_ID}",
        lambda data: data and data.get("prices"),
        timeout=60
    )
    
    # --- 4. Ingest Day 1 Transaction ---
    deposit_payload = {"transactions": [{"transaction_id": DEPOSIT_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1.0, "gross_transaction_amount": 1000000.0, "trade_currency": "USD", "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=deposit_payload)

    # --- 5. Poll DB for the final result of the pipeline ---
    timeout = 90
    start_time = time.time()
    with Session(db_engine) as session:
        while time.time() - start_time < timeout:
            port_ts_query = text("SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date")
            result = session.execute(port_ts_query, {"pid": PORTFOLIO_ID, "date": DAY_1}).fetchone()
            if result:
                break
            time.sleep(3)
        else:
            pytest.fail("Polling timed out waiting for portfolio_timeseries record for Day 1.")

    yield # This fixture provides setup only, no data is returned

def test_workflow_day1_verification(setup_and_verify_day1_state, db_engine):
    """
    Verifies the entire database state after the Day 1 cash deposit pipeline is complete.
    """
    with Session(db_engine) as session:
        # 1. Verify Portfolio
        portfolio_query = text("SELECT portfolio_id FROM portfolios WHERE portfolio_id = :pid")
        portfolio_result = session.execute(portfolio_query, {"pid": PORTFOLIO_ID}).fetchone()
        assert portfolio_result is not None

        # 2. Verify Instruments
        instrument_query = text("SELECT count(*) FROM instruments WHERE security_id = ANY(:ids)")
        instrument_count = session.execute(instrument_query, {"ids": [CASH_USD_ID, CASH_EUR_ID, AAPL_ID, IBM_ID]}).scalar()
        assert instrument_count == 4

        # 3. Verify Prices
        price_query = text("SELECT count(*) FROM market_prices WHERE price_date = '2025-08-18'")
        price_count = session.execute(price_query).scalar()
        assert price_count == 4
        
        # 4. Verify Cashflow record
        cf_query = text("SELECT security_id, amount, is_position_flow, is_portfolio_flow FROM cashflows WHERE transaction_id = :txn_id")
        cf_result = session.execute(cf_query, {"txn_id": DEPOSIT_TXN_ID}).fetchone()
        assert cf_result is not None
        assert cf_result.security_id == CASH_USD_ID
        assert cf_result.is_position_flow is True
        assert cf_result.is_portfolio_flow is True

        # 5. Verify Position History
        ph_query = text("SELECT quantity, cost_basis FROM position_history WHERE transaction_id = :txn_id")
        ph_result = session.execute(ph_query, {"txn_id": DEPOSIT_TXN_ID}).fetchone()
        assert ph_result is not None
        assert ph_result.quantity == Decimal("1000000.0000000000")

        # 6. Verify Position Timeseries
        pts_query = text("SELECT bod_cashflow_position, bod_cashflow_portfolio FROM position_timeseries WHERE portfolio_id = :pid AND security_id = :sid AND date = :date")
        pts_result = session.execute(pts_query, {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_1}).fetchone()
        assert pts_result is not None
        assert pts_result.bod_cashflow_position == Decimal("1000000.0000000000")
        assert pts_result.bod_cashflow_portfolio == Decimal("1000000.0000000000")

        # 7. Verify Portfolio Timeseries
        port_ts_query = text("SELECT bod_cashflow, eod_market_value FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date")
        port_ts_result = session.execute(port_ts_query, {"pid": PORTFOLIO_ID, "date": DAY_1}).fetchone()
        assert port_ts_result is not None
        assert port_ts_result.bod_cashflow == Decimal("1000000.0000000000")
        assert port_ts_result.eod_market_value == Decimal("1000000.0000000000")