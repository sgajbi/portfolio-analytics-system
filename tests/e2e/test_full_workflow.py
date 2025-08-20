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

    # --- 1. Ingest Portfolio, Instruments, and Prices ---
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": BASE_CURRENCY, "openDate": "2025-01-01", "cifId": "WF_CIF_01", "status": "ACTIVE", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": CASH_USD_ID, "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash"}, {"securityId": CASH_EUR_ID, "name": "Euro", "isin": "CASH_EUR_ISIN", "instrumentCurrency": "EUR", "productType": "Cash"}, {"securityId": AAPL_ID, "name": "Apple Inc.", "isin": "US0378331005", "instrumentCurrency": "USD", "productType": "Equity"}, {"securityId": IBM_ID, "name": "IBM Corp.", "isin": "US4592001014", "instrumentCurrency": "USD", "productType": "Equity"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": CASH_USD_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "USD"}, {"securityId": CASH_EUR_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "EUR"}, {"securityId": AAPL_ID, "priceDate": "2025-08-18", "price": 175.0, "currency": "USD"}, {"securityId": IBM_ID, "priceDate": "2025-08-18", "price": 150.0, "currency": "USD"}]})

    # --- 2. Ingest Day 1 Transaction (Cash Deposit) ---
    deposit_payload = {"transactions": [{"transaction_id": DEPOSIT_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1.0, "gross_transaction_amount": 1000000.0, "trade_currency": "USD", "currency": "USD"}]}
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=deposit_payload)
    assert response.status_code == 202, f"Failed to ingest Day 1 transaction: {response.text}"

    # --- 3. Poll DB for the final result of the pipeline ---
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
        # 1. Verify Transaction
        txn_query = text("SELECT net_cost, gross_cost FROM transactions WHERE transaction_id = :txn_id")
        txn_result = session.execute(txn_query, {"txn_id": DEPOSIT_TXN_ID}).fetchone()

        # 2. Verify Cashflow
        cf_query = text("SELECT security_id, amount, is_position_flow, is_portfolio_flow FROM cashflows WHERE transaction_id = :txn_id")
        cf_result = session.execute(cf_query, {"txn_id": DEPOSIT_TXN_ID}).fetchone()
        
        # 3. Verify Position History
        ph_query = text("SELECT quantity, cost_basis FROM position_history WHERE transaction_id = :txn_id")
        ph_result = session.execute(ph_query, {"txn_id": DEPOSIT_TXN_ID}).fetchone()

        # 4. Verify Position Timeseries
        pts_query = text("SELECT bod_cashflow_position, bod_cashflow_portfolio, created_at IS NOT NULL AS has_created_at FROM position_timeseries WHERE portfolio_id = :pid AND security_id = :sid AND date = :date")
        pts_result = session.execute(pts_query, {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_1}).fetchone()

        # 5. Verify Portfolio Timeseries
        port_ts_query = text("SELECT bod_cashflow, eod_market_value, created_at IS NOT NULL AS has_created_at FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date")
        port_ts_result = session.execute(port_ts_query, {"pid": PORTFOLIO_ID, "date": DAY_1}).fetchone()

    # Assert Transaction
    assert txn_result is not None, "Transaction record not found for deposit."
    assert txn_result.net_cost == Decimal("1000000.0000000000")
    assert txn_result.gross_cost == Decimal("1000000.0000000000")

    # Assert Cashflow
    assert cf_result is not None, "Cashflow record not found for deposit."
    assert cf_result.security_id == CASH_USD_ID
    assert cf_result.is_position_flow is True
    assert cf_result.is_portfolio_flow is True

    # Assert Position History
    assert ph_result is not None, "Position history not found for deposit."
    assert ph_result.quantity == Decimal("1000000.0000000000")

    # Assert Position Timeseries
    assert pts_result is not None, "Position timeseries not found for cash deposit."
    assert pts_result.bod_cashflow_position == Decimal("1000000.0000000000")
    assert pts_result.bod_cashflow_portfolio == Decimal("1000000.0000000000")
    assert pts_result.has_created_at is True

    # Assert Portfolio Timeseries
    assert port_ts_result is not None, "Portfolio timeseries not found for Day 1."
    assert port_ts_result.bod_cashflow == Decimal("1000000.0000000000")
    assert port_ts_result.eod_market_value == Decimal("1000000.0000000000")
    assert port_ts_result.has_created_at is True