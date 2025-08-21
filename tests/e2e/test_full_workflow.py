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

DEPOSIT_TXN_ID = "TXN_DAY1_DEPOSIT_01"
BUY_AAPL_TXN_ID = "TXN_DAY2_BUY_AAPL_01"
SELL_CASH_D2_TXN_ID = "TXN_DAY2_SELL_CASH_01"
BUY_IBM_TXN_ID = "TXN_DAY3_BUY_IBM_01"
SELL_CASH_D3_TXN_ID = "TXN_DAY3_SELL_CASH_01"
SELL_AAPL_TXN_ID = "TXN_DAY4_SELL_AAPL_01"
BUY_CASH_D4_TXN_ID = "TXN_DAY4_BUY_CASH_01"

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
    ]}
    requests.post(f"{ingestion_url}/ingest/business-dates", json=business_dates_payload)
    
    # Allow a moment for prerequisites to persist
    time.sleep(5)
    yield

# --- Test Functions (Sequential) ---

@pytest.mark.dependency()
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
        cash_r1 = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_1}).fetchone()
        assert cash_r1 and cash_r1.quantity == Decimal("1000000.0000000000")

@pytest.mark.dependency(depends=["test_day1_deposit"])
def test_day2_aapl_buy(api_endpoints, db_engine):
    """Ingests Day 2 data and verifies the final state for that day."""
    ingestion_url = api_endpoints["ingestion"]

    # Ingest Day 2 Transactions & Prices
    day2_buy_payload = {"transactions": [{"transaction_id": BUY_AAPL_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": AAPL_ID, "security_id": AAPL_ID, "transaction_date": f"{DAY_2}T15:30:00Z", "transaction_type": "BUY", "quantity": 500, "price": 176.0, "gross_transaction_amount": 88000.0, "trade_fee": 25.0, "trade_currency": "USD", "currency": "USD"}]}
    day2_sell_cash_payload = {"transactions": [{"transaction_id": SELL_CASH_D2_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_2}T15:30:00Z", "transaction_type": "SELL", "quantity": 88025.0, "price": 1.0, "gross_transaction_amount": 88025.0, "trade_currency": "USD", "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=day2_buy_payload)
    requests.post(f"{ingestion_url}/ingest/transactions", json=day2_sell_cash_payload)

    day2_prices_payload = {"market_prices": [
        {"securityId": AAPL_ID, "priceDate": DAY_2, "price": 178.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_2, "price": 1.0, "currency": "USD"}
    ]}
    requests.post(f"{ingestion_url}/ingest/market-prices", json=day2_prices_payload)

    # Poll for the final state of Day 2
    poll_db_until(
        db_engine=db_engine,
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": PORTFOLIO_ID, "date": DAY_2},
        validation_func=lambda result: result is not None,
        fail_message="Pipeline did not create portfolio_timeseries record for Day 2."
    )

    # Assert Day 2 State
    with Session(db_engine) as session:
        aapl_r2 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": AAPL_ID, "date": DAY_2}).fetchone()
        assert aapl_r2 and aapl_r2.quantity == Decimal("500.0000000000")
        assert aapl_r2.cost_basis == Decimal("88025.0000000000")
        assert aapl_r2.market_value == Decimal("89000.0000000000")

        cash_r2 = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_2}).fetchone()
        assert cash_r2 and cash_r2.quantity == Decimal("911975.0000000000")

@pytest.mark.dependency(depends=["test_day2_aapl_buy"])
def test_day3_ibm_buy(api_endpoints, db_engine):
    """Ingests Day 3 data and verifies the final state, including roll-forwards."""
    ingestion_url = api_endpoints["ingestion"]

    # Ingest Day 3 Transactions & Prices
    day3_buy_payload = {"transactions": [{"transaction_id": BUY_IBM_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": IBM_ID, "security_id": IBM_ID, "transaction_date": f"{DAY_3}T16:00:00Z", "transaction_type": "BUY", "quantity": 300, "price": 150.0, "gross_transaction_amount": 45000.0, "trade_fee": 20.0, "trade_currency": "USD", "currency": "USD"}]}
    day3_sell_cash_payload = {"transactions": [{"transaction_id": SELL_CASH_D3_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_3}T16:00:00Z", "transaction_type": "SELL", "quantity": 45020.0, "price": 1.0, "gross_transaction_amount": 45020.0, "trade_currency": "USD", "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=day3_buy_payload)
    requests.post(f"{ingestion_url}/ingest/transactions", json=day3_sell_cash_payload)

    day3_prices_payload = {"market_prices": [
        {"securityId": AAPL_ID, "priceDate": DAY_3, "price": 180.0, "currency": "USD"},
        {"securityId": IBM_ID, "priceDate": DAY_3, "price": 152.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_3, "price": 1.0, "currency": "USD"}
    ]}
    requests.post(f"{ingestion_url}/ingest/market-prices", json=day3_prices_payload)

    # Poll for the final state of Day 3, specifically for the corrected AAPL value
    poll_db_until(
        db_engine=db_engine,
        query="SELECT market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date",
        params={"pid": PORTFOLIO_ID, "sid": AAPL_ID, "date": DAY_3},
        validation_func=lambda result: result is not None and result.market_value == Decimal("90000.0000000000"),
        fail_message="Pipeline did not correctly re-value AAPL snapshot for Day 3."
    )

    # Assert Day 3 State
    with Session(db_engine) as session:
        aapl_r3 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": AAPL_ID, "date": DAY_3}).fetchone()
        assert aapl_r3, "AAPL snapshot for Day 3 not found"
        assert aapl_r3.quantity == Decimal("500.0000000000")
        assert aapl_r3.cost_basis == Decimal("88025.0000000000")
        assert aapl_r3.market_value == Decimal("90000.0000000000")

        ibm_r3 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": IBM_ID, "date": DAY_3}).fetchone()
        assert ibm_r3, "IBM snapshot for Day 3 not found"
        assert ibm_r3.quantity == Decimal("300.0000000000")
        assert ibm_r3.cost_basis == Decimal("45020.0000000000")
        assert ibm_r3.market_value == Decimal("45600.0000000000")

        cash_r3 = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_3}).fetchone()
        assert cash_r3, "Cash snapshot for Day 3 not found"
        assert cash_r3.quantity == Decimal("866955.0000000000")

@pytest.mark.dependency(depends=["test_day3_ibm_buy"])
def test_day4_aapl_sell(api_endpoints, db_engine):
    """Ingests Day 4 data and verifies the final state."""
    ingestion_url = api_endpoints["ingestion"]

    # Ingest Day 4 Transactions & Prices
    day4_sell_aapl_payload = {"transactions": [{"transaction_id": SELL_AAPL_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": AAPL_ID, "security_id": AAPL_ID, "transaction_date": f"{DAY_4}T11:00:00Z", "transaction_type": "SELL", "quantity": 100, "price": 182.0, "gross_transaction_amount": 18200.0, "trade_fee": 15.0, "trade_currency": "USD", "currency": "USD"}]}
    day4_buy_cash_payload = {"transactions": [{"transaction_id": BUY_CASH_D4_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_4}T11:00:00Z", "transaction_type": "BUY", "quantity": 18185.0, "price": 1.0, "gross_transaction_amount": 18185.0, "trade_currency": "USD", "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=day4_sell_aapl_payload)
    requests.post(f"{ingestion_url}/ingest/transactions", json=day4_buy_cash_payload)

    day4_prices_payload = {"market_prices": [
        {"securityId": AAPL_ID, "priceDate": DAY_4, "price": 183.0, "currency": "USD"},
        {"securityId": IBM_ID, "priceDate": DAY_4, "price": 151.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_4, "price": 1.0, "currency": "USD"}
    ]}
    requests.post(f"{ingestion_url}/ingest/market-prices", json=day4_prices_payload)

    # Poll for the final state of Day 4
    poll_db_until(
        db_engine=db_engine,
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": PORTFOLIO_ID, "date": DAY_4},
        validation_func=lambda result: result is not None,
        fail_message="Pipeline did not create portfolio_timeseries record for Day 4."
    )

    # Assert Day 4 State
    with Session(db_engine) as session:
        aapl_r4 = session.execute(text("SELECT quantity, cost_basis, market_value, unrealized_gain_loss FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": AAPL_ID, "date": DAY_4}).fetchone()
        assert aapl_r4, "AAPL snapshot for Day 4 not found"
        assert aapl_r4.quantity == Decimal("400.0000000000")
        assert aapl_r4.cost_basis == Decimal("70420.0000000000")
        assert aapl_r4.market_value == Decimal("73200.0000000000")
        assert aapl_r4.unrealized_gain_loss == Decimal("2780.0000000000")

        ibm_r4 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": IBM_ID, "date": DAY_4}).fetchone()
        assert ibm_r4, "IBM snapshot for Day 4 not found"
        assert ibm_r4.quantity == Decimal("300.0000000000")
        assert ibm_r4.cost_basis == Decimal("45020.0000000000")
        assert ibm_r4.market_value == Decimal("45300.0000000000")

        cash_r4 = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_4}).fetchone()
        assert cash_r4, "Cash snapshot for Day 4 not found"
        assert cash_r4.quantity == Decimal("885140.0000000000")

        sell_txn = session.execute(text("SELECT realized_gain_loss FROM transactions WHERE transaction_id = :tid"), {"tid": SELL_AAPL_TXN_ID}).fetchone()
        assert sell_txn, "AAPL SELL transaction not found"
        assert sell_txn.realized_gain_loss == Decimal("580.0000000000")