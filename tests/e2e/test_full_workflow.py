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
IBM_ID = "SEC_IBM_E2E" # New Instrument

DAY_1 = "2025-08-19"
DAY_2 = "2025-08-20"
DAY_3 = "2025-08-21" # New Day

DEPOSIT_TXN_ID = "TXN_DAY1_DEPOSIT_01"
BUY_AAPL_TXN_ID = "TXN_DAY2_BUY_AAPL_01"
SELL_CASH_TXN_ID_DAY2 = "TXN_DAY2_SELL_CASH_01"
BUY_IBM_TXN_ID = "TXN_DAY3_BUY_IBM_01" # New Transaction
SELL_CASH_TXN_ID_DAY3 = "TXN_DAY3_SELL_CASH_01" # New Transaction


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
def setup_workflow_data(clean_db_module, api_endpoints, db_engine):
    """
    A module-scoped, idempotent fixture that ingests all data for the Day 1, 2, and 3
    workflow, validates each step, and polls until the full pipeline is complete.
    """
    ingestion_url = api_endpoints["ingestion"]

    # --- Ingest Setup Data ---
    portfolio_payload = {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "WF_CIF_01", "status": "ACTIVE", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG"}]}
    response = requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload)
    assert response.status_code == 202, f"Failed to ingest portfolio: {response.text}"

    instruments_payload = {"instruments": [
        {"securityId": CASH_USD_ID, "name": "US Dollar", "instrumentCurrency": "USD", "productType": "Cash", "isin": "CASH_USD_ISIN"},
        {"securityId": AAPL_ID, "name": "Apple Inc.", "instrumentCurrency": "USD", "productType": "Equity", "isin": "US0378331005"},
        {"securityId": IBM_ID, "name": "IBM Corp.", "instrumentCurrency": "USD", "productType": "Equity", "isin": "US4592001014"}
    ]}
    response = requests.post(f"{ingestion_url}/ingest/instruments", json=instruments_payload)
    assert response.status_code == 202, f"Failed to ingest instruments: {response.text}"

    # --- Day 1 Ingestion ---
    day1_deposit_payload = {"transactions": [{"transaction_id": DEPOSIT_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1.0, "gross_transaction_amount": 1000000.0, "trade_currency": "USD", "currency": "USD"}]}
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day1_deposit_payload)
    assert response.status_code == 202, f"Failed to ingest Day 1 transaction: {response.text}"

    # --- Day 2 Ingestion ---
    day2_buy_payload = {"transactions": [{"transaction_id": BUY_AAPL_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": AAPL_ID, "security_id": AAPL_ID, "transaction_date": f"{DAY_2}T15:30:00Z", "transaction_type": "BUY", "quantity": 500, "price": 176.0, "gross_transaction_amount": 88000.0, "trade_fee": 25.0, "trade_currency": "USD", "currency": "USD"}]}
    day2_sell_cash_payload = {"transactions": [{"transaction_id": SELL_CASH_TXN_ID_DAY2, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_2}T15:30:00Z", "transaction_type": "SELL", "quantity": 88025.0, "price": 1.0, "gross_transaction_amount": 88025.0, "trade_currency": "USD", "currency": "USD"}]}
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day2_buy_payload)
    assert response.status_code == 202, f"Failed to ingest Day 2 BUY transaction: {response.text}"
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day2_sell_cash_payload)
    assert response.status_code == 202, f"Failed to ingest Day 2 SELL CASH transaction: {response.text}"

    # --- Day 3 Ingestion ---
    day3_buy_payload = {"transactions": [{"transaction_id": BUY_IBM_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": IBM_ID, "security_id": IBM_ID, "transaction_date": f"{DAY_3}T16:00:00Z", "transaction_type": "BUY", "quantity": 300, "price": 150.0, "gross_transaction_amount": 45000.0, "trade_fee": 20.0, "trade_currency": "USD", "currency": "USD"}]}
    day3_sell_cash_payload = {"transactions": [{"transaction_id": SELL_CASH_TXN_ID_DAY3, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_3}T16:00:00Z", "transaction_type": "SELL", "quantity": 45020.0, "price": 1.0, "gross_transaction_amount": 45020.0, "trade_currency": "USD", "currency": "USD"}]}
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day3_buy_payload)
    assert response.status_code == 202, f"Failed to ingest Day 3 BUY transaction: {response.text}"
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day3_sell_cash_payload)
    assert response.status_code == 202, f"Failed to ingest Day 3 SELL CASH transaction: {response.text}"

    # --- Ingest All Market Prices ---
    prices_payload = {"market_prices": [
        {"securityId": AAPL_ID, "priceDate": DAY_2, "price": 178.0, "currency": "USD"},
        {"securityId": AAPL_ID, "priceDate": DAY_3, "price": 180.0, "currency": "USD"},
        {"securityId": IBM_ID, "priceDate": DAY_3, "price": 152.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_1, "price": 1.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_2, "price": 1.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_3, "price": 1.0, "currency": "USD"}
    ]}
    response = requests.post(f"{ingestion_url}/ingest/market-prices", json=prices_payload)
    assert response.status_code == 202, f"Failed to ingest prices: {response.text}"

    # --- Poll for Final State ---
    poll_db_until(
        db_engine=db_engine,
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": PORTFOLIO_ID, "date": DAY_3},
        validation_func=lambda result: result is not None,
        fail_message="Pipeline did not create portfolio_timeseries record for Day 3."
    )
    yield

# --- Test Function ---

def test_full_workflow_verification(setup_workflow_data, db_engine, api_endpoints):
    """
    Performs a comprehensive verification of the database state and Performance API
    response after the Day 1, 2, and 3 workflow is complete.
    """
    # --- ARRANGE ---
    query_url = api_endpoints["query"]

    # --- ACT & ASSERT: Database State Verification ---
    with Session(db_engine) as session:
        # Day 2 AAPL Position
        aapl_r2 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": AAPL_ID, "date": DAY_2}).fetchone()
        assert aapl_r2 and aapl_r2.quantity == Decimal("500.0000000000")
        assert aapl_r2.cost_basis == Decimal("88025.0000000000")
        assert aapl_r2.market_value == Decimal("89000.0000000000") # 500 * 178

        # Day 3 AAPL Position (Rolled forward quantity/cost, new MV)
        aapl_r3 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": AAPL_ID, "date": DAY_3}).fetchone()
        assert aapl_r3 and aapl_r3.quantity == Decimal("500.0000000000")
        assert aapl_r3.cost_basis == Decimal("88025.0000000000")
        assert aapl_r3.market_value == Decimal("90000.0000000000") # 500 * 180

        # Day 3 IBM Position (New)
        ibm_r3 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": IBM_ID, "date": DAY_3}).fetchone()
        assert ibm_r3 and ibm_r3.quantity == Decimal("300.0000000000")
        assert ibm_r3.cost_basis == Decimal("45020.0000000000")
        assert ibm_r3.market_value == Decimal("45600.0000000000") # 300 * 152

        # Day 3 Cash Position
        cash_r3 = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_3}).fetchone()
        # 1,000,000 (deposit) - 88,025 (AAPL buy) - 45,020 (IBM buy) = 866,955
        assert cash_r3 and cash_r3.quantity == Decimal("866955.0000000000")

    # --- ACT & ASSERT: Performance API Response as of Day 3 ---
    perf_payload = {
        "scope": { "as_of_date": DAY_3, "net_or_gross": "NET" },
        "periods": [{ "name": "Since Inception", "type": "SI" }],
        "options": { "include_attributes": True, "include_cumulative": True, "include_annualized": False }
    }
    response = requests.post(f"{query_url}/portfolios/{PORTFOLIO_ID}/performance", json=perf_payload)
    assert response.status_code == 200, f"Performance API failed: {response.text}"
    perf_data = response.json()

    # --- Assert Performance Summary ---
    # Expected EOD MV (Day 3) = 90000 (AAPL) + 45600 (IBM) + 866955 (Cash) = 1,002,555
    # Expected Total Cashflow = 1,000,000 (Deposit)
    # Expected Return = (1,002,555 - 1,000,000) / 1,000,000 = 0.2555%
    summary_result = perf_data["summary"]["Since Inception"]
    assert pytest.approx(summary_result["cumulative_return"], abs=1e-4) == 0.2555
    assert Decimal(summary_result["attributes"]["end_market_value"]).quantize(Decimal("0.01")) == Decimal("1002555.00")
    assert Decimal(summary_result["attributes"]["total_cashflow"]).quantize(Decimal("0.01")) == Decimal("1000000.00")