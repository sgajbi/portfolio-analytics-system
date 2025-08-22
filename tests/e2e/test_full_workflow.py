# tests/e2e/test_full_workflow.py
import pytest
import requests
import time
import logging
from sqlalchemy import text, Engine
from sqlalchemy.orm import Session
from datetime import date
from decimal import Decimal
from typing import Callable, Any

# --- Constants ---
PORTFOLIO_ID = "E2E_WORKFLOW_01"
CASH_USD_ID = "CASH_USD"
AAPL_ID = "SEC_AAPL_E2E"
IBM_ID = "SEC_IBM_E2E" 

DAY_1 = "2025-08-19"
DAY_2 = "2025-08-20"
DAY_3 = "2025-08-21"
DAY_4 = "2025-08-22"
DAY_5 = "2025-08-23"

DEPOSIT_TXN_ID = "TXN_DAY1_DEPOSIT_01"
# --- End Constants ---


# --- Helper Functions ---

def poll_db_until(
    db_engine: Engine,
    query: str,
    validation_func: Callable[[Any], bool],
    params: dict = {},
    timeout: int = 90,
    interval: int = 3,
    fail_message: str = "Polling timed out."
):
    """
    Polls the database by executing a query until a validation function returns True.
    """
    start_time = time.time()
    last_result = None
    while time.time() - start_time < timeout:
        with Session(db_engine) as session:
            result = session.execute(text(query), params).fetchone()
            last_result = result
            if validation_func(result):
                return
        time.sleep(interval)
    
    logging.error(f"POLLING FAILED: {fail_message}")
    logging.error(f"Last result from DB query was: {last_result}")
    pytest.fail(fail_message)

# --- Test Fixture ---

@pytest.fixture(scope="module")
def setup_prerequisites(clean_db_module, api_endpoints):
    """
    A module-scoped fixture that ingests all prerequisite data that does not change daily:
    Portfolio, Instruments, and Business Dates for the entire test period.
    """
    ingestion_url = api_endpoints["ingestion"]

    # Ingest Portfolio and Instruments
    portfolio_payload = {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "WF_CIF_01", "status": "ACTIVE", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG"}]}
    requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload)

    instruments_payload = {"instruments": [
        {"securityId": CASH_USD_ID, "name": "US Dollar", "instrumentCurrency": "USD", "productType": "Cash", "isin": "CASH_USD_ISIN"},
        {"securityId": AAPL_ID, "name": "Apple Inc.", "instrumentCurrency": "USD", "productType": "Equity", "isin": "US0378331005"},
        {"securityId": IBM_ID, "name": "IBM Corp.", "instrumentCurrency": "USD", "productType": "Equity", "isin": "US4592001014"}
    ]}
    requests.post(f"{ingestion_url}/ingest/instruments", json=instruments_payload)

    # Ingest all business dates upfront to drive the scheduler correctly
    business_dates_payload = {"business_dates": [
        {"businessDate": DAY_1},
        {"businessDate": DAY_2},
        {"businessDate": DAY_3},
        {"businessDate": DAY_4},
        {"businessDate": DAY_5},
    ]}
    requests.post(f"{ingestion_url}/ingest/business-dates", json=business_dates_payload)
    
    # Allow a moment for prerequisites to persist
    time.sleep(5)
    yield


# --- Test Functions (Sequential) ---

@pytest.mark.dependency()
def test_prerequisites_loaded(setup_prerequisites, db_engine):
    """
    Verifies that the portfolio and instruments were ingested correctly.
    """
    with Session(db_engine) as session:
        # Verify Portfolio
        portfolio_count = session.execute(text("SELECT count(*) FROM portfolios WHERE portfolio_id = :pid"), {"pid": PORTFOLIO_ID}).scalar()
        assert portfolio_count == 1, f"Portfolio {PORTFOLIO_ID} was not created."

        # Verify Instruments
        instrument_ids = [CASH_USD_ID, AAPL_ID, IBM_ID]
        instrument_count = session.execute(text("SELECT count(*) FROM instruments WHERE security_id IN :ids"), {"ids": tuple(instrument_ids)}).scalar()
        assert instrument_count == 3, "Not all instruments were created."

        # Verify Business Dates
        date_count = session.execute(text("SELECT count(*) FROM business_dates WHERE date >= :start"), {"start": DAY_1}).scalar()
        assert date_count == 5, "Not all business dates were created."


@pytest.mark.dependency(depends=["test_prerequisites_loaded"])
def test_day1_deposit(setup_prerequisites, api_endpoints, db_engine):
    """Ingests Day 1 data and verifies the final state for that day."""
    ingestion_url = api_endpoints["ingestion"]

    # Ingest Day 1 Transaction & Price Data
    day1_deposit_payload = {"transactions": [{"transaction_id": DEPOSIT_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1.0, "gross_transaction_amount": 1000000.0, "trade_currency": "USD", "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=day1_deposit_payload)
    
    day1_prices_payload = {"market_prices": [{"securityId": CASH_USD_ID, "priceDate": DAY_1, "price": 1.0, "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/market-prices", json=day1_prices_payload)

    # Poll for the final state of Day 1
    poll_db_until(
        db_engine=db_engine,
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": PORTFOLIO_ID, "date": DAY_1},
        validation_func=lambda result: result is not None,
        fail_message="Pipeline did not create portfolio_timeseries record for Day 1."
    )

    # Assert Day 1 State
    with Session(db_engine) as session:
        cash_snapshot = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_1}).fetchone()
        assert cash_snapshot is not None, "Cash position snapshot for Day 1 not found."
        assert cash_snapshot.quantity == Decimal("1000000.0000000000")