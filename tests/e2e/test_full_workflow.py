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
def setup_workflow_data(clean_db_module, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that sets up the initial state for the full workflow test.
    This fixture ingests the portfolio, instruments, prices, and Day 1 transaction.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]

    # --- 1. Ingest Portfolio, Instruments, and Prices ---
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": BASE_CURRENCY, "openDate": "2025-01-01", "cifId": "WF_CIF_01", "status": "ACTIVE", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": CASH_USD_ID, "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash"}, {"securityId": CASH_EUR_ID, "name": "Euro", "isin": "CASH_EUR_ISIN", "instrumentCurrency": "EUR", "productType": "Cash"}, {"securityId": AAPL_ID, "name": "Apple Inc.", "isin": "US0378331005", "instrumentCurrency": "USD", "productType": "Equity"}, {"securityId": IBM_ID, "name": "IBM Corp.", "isin": "US4592001014", "instrumentCurrency": "USD", "productType": "Equity"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": CASH_USD_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "USD"}, {"securityId": CASH_EUR_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "EUR"}, {"securityId": AAPL_ID, "priceDate": "2025-08-18", "price": 175.0, "currency": "USD"}, {"securityId": IBM_ID, "priceDate": "2025-08-18", "price": 150.0, "currency": "USD"}]})

    # --- 2. Ingest Day 1 Transaction (Cash Deposit) ---
    deposit_payload = {
        "transactions": [{"transaction_id": DEPOSIT_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1.0, "gross_transaction_amount": 1000000.0, "trade_currency": "USD", "currency": "USD"}]
    }
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=deposit_payload)
    assert response.status_code == 202, f"Failed to ingest Day 1 transaction: {response.text}"

    # --- 3. Verification will happen in the test function itself ---
    yield {
        "ingestion_url": ingestion_url,
        "query_url": query_url
    }

def test_workflow_step1_portfolio_and_instrument_creation(setup_workflow_data, db_engine):
    """
    Verifies that the portfolio and instruments were created correctly in the database.
    """
    expected_instrument_ids = {CASH_USD_ID, CASH_EUR_ID, AAPL_ID, IBM_ID}
    with Session(db_engine) as session:
        portfolio_query = text("SELECT portfolio_id, base_currency, status FROM portfolios WHERE portfolio_id = :pid")
        portfolio_result = session.execute(portfolio_query, {"pid": PORTFOLIO_ID}).fetchone()
        instrument_query = text("SELECT security_id FROM instruments WHERE security_id = ANY(:ids)")
        instrument_results = session.execute(instrument_query, {"ids": list(expected_instrument_ids)}).fetchall()
    assert portfolio_result is not None, f"Portfolio {PORTFOLIO_ID} not found."
    assert portfolio_result.portfolio_id == PORTFOLIO_ID
    persisted_instrument_ids = {row[0] for row in instrument_results}
    assert persisted_instrument_ids == expected_instrument_ids, "Mismatch in persisted instruments."

def test_workflow_step2_price_setup(setup_workflow_data, db_engine):
    """
    Verifies that the market prices were created correctly in the database.
    """
    price_date = "2025-08-18"
    with Session(db_engine) as session:
        price_query = text("SELECT security_id, price FROM market_prices WHERE price_date = :p_date")
        price_results = session.execute(price_query, {"p_date": price_date}).fetchall()
    assert len(price_results) == 4, "Expected 4 price records for the given date."
    prices_map = {row[0]: row[1] for row in price_results}
    assert prices_map[CASH_USD_ID] == Decimal("1.0000000000")
    assert prices_map[AAPL_ID] == Decimal("175.0000000000")
    assert prices_map[IBM_ID] == Decimal("150.0000000000")

def test_workflow_day1_cash_deposit(setup_workflow_data, db_engine):
    """
    Verifies the entire pipeline state after a Day 1 cash deposit.
    """
    # ARRANGE: Poll the database directly for the final portfolio_timeseries record
    # This is a more reliable way to wait for the entire async pipeline to finish.
    timeout = 60
    start_time = time.time()
    port_ts_result = None
    with Session(db_engine) as session:
        while time.time() - start_time < timeout:
            port_ts_query = text("SELECT bod_cashflow, eod_market_value FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date")
            port_ts_result = session.execute(port_ts_query, {"pid": PORTFOLIO_ID, "date": DAY_1}).fetchone()
            if port_ts_result:
                break
            time.sleep(2)

    # ASSERT: Now run all assertions now that we know the data is ready
    assert port_ts_result is not None, "Portfolio timeseries not found for Day 1 after polling."
    assert port_ts_result.bod_cashflow == Decimal("1000000.0000000000")
    assert port_ts_result.eod_market_value == Decimal("1000000.0000000000")

    with Session(db_engine) as session:
        # Verify the other tables now that the final state is confirmed
        cf_query = text("SELECT security_id, amount, classification, is_position_flow, is_portfolio_flow FROM cashflows WHERE transaction_id = :txn_id")
        cf_result = session.execute(cf_query, {"txn_id": DEPOSIT_TXN_ID}).fetchone()
        
        ph_query = text("SELECT quantity, cost_basis FROM position_history WHERE transaction_id = :txn_id")
        ph_result = session.execute(ph_query, {"txn_id": DEPOSIT_TXN_ID}).fetchone()

        pts_query = text("SELECT bod_cashflow_position, bod_cashflow_portfolio, eod_market_value FROM position_timeseries WHERE portfolio_id = :pid AND security_id = :sid AND date = :date")
        pts_result = session.execute(pts_query, {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_1}).fetchone()

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