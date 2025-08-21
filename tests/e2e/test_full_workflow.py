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

DAY_1 = "2025-08-19"
DAY_2 = "2025-08-20"

DEPOSIT_TXN_ID = "TXN_DAY1_DEPOSIT_01"
BUY_AAPL_TXN_ID = "TXN_DAY2_BUY_AAPL_01"
SELL_CASH_TXN_ID = "TXN_DAY2_SELL_CASH_01"

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
def setup_day2_workflow(clean_db_module, api_endpoints, db_engine):
    """
    A module-scoped, idempotent fixture that ingests all data for the Day 1 and Day 2
    workflow, validates each step, and polls until the full pipeline is complete.
    """
    ingestion_url = api_endpoints["ingestion"]

    # --- Ingest Setup Data ---
    portfolio_payload = {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "WF_CIF_01", "status": "ACTIVE", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG"}]}
    response = requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload)
    assert response.status_code == 202, f"Failed to ingest portfolio: {response.text}"

    instruments_payload = {"instruments": [
        {"securityId": CASH_USD_ID, "name": "US Dollar", "instrumentCurrency": "USD", "productType": "Cash", "isin": "CASH_USD_ISIN"},
        {"securityId": AAPL_ID, "name": "Apple Inc.", "instrumentCurrency": "USD", "productType": "Equity", "isin": "US0378331005"}
    ]}
    response = requests.post(f"{ingestion_url}/ingest/instruments", json=instruments_payload)
    assert response.status_code == 202, f"Failed to ingest instruments: {response.text}"

    prices_payload = {"market_prices": [
        {"securityId": CASH_USD_ID, "priceDate": DAY_1, "price": 1.0, "currency": "USD"},
        {"securityId": AAPL_ID, "priceDate": DAY_1, "price": 175.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_2, "price": 1.0, "currency": "USD"},
        {"securityId": AAPL_ID, "priceDate": DAY_2, "price": 178.0, "currency": "USD"}
    ]}
    response = requests.post(f"{ingestion_url}/ingest/market-prices", json=prices_payload)
    assert response.status_code == 202, f"Failed to ingest prices: {response.text}"

    # --- Day 1 Ingestion (FIXED PAYLOAD) ---
    day1_payload = {"transactions": [{"transaction_id": DEPOSIT_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1.0, "gross_transaction_amount": 1000000.0, "trade_currency": "USD", "currency": "USD"}]}
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day1_payload)
    assert response.status_code == 202, f"Failed to ingest Day 1 transaction: {response.text}"

    # --- Day 2 Ingestion (FIXED PAYLOADS) ---
    day2_buy_payload = {"transactions": [{"transaction_id": BUY_AAPL_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": AAPL_ID, "security_id": AAPL_ID, "transaction_date": f"{DAY_2}T15:30:00Z", "transaction_type": "BUY", "quantity": 500, "price": 176.0, "gross_transaction_amount": 88000.0, "trade_fee": 25.0, "trade_currency": "USD", "currency": "USD"}]}
    day2_sell_cash_payload = {"transactions": [{"transaction_id": SELL_CASH_TXN_ID, "portfolio_id": PORTFOLIO_ID, "instrument_id": CASH_USD_ID, "security_id": CASH_USD_ID, "transaction_date": f"{DAY_2}T15:30:00Z", "transaction_type": "SELL", "quantity": 88025.0, "price": 1.0, "gross_transaction_amount": 88025.0, "trade_currency": "USD", "currency": "USD"}]}
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day2_buy_payload)
    assert response.status_code == 202, f"Failed to ingest Day 2 BUY transaction: {response.text}"
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=day2_sell_cash_payload)
    assert response.status_code == 202, f"Failed to ingest Day 2 SELL CASH transaction: {response.text}"

    # --- Poll for Final State ---
    poll_db_until(
        db_engine=db_engine,
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": PORTFOLIO_ID, "date": DAY_2},
        validation_func=lambda result: result is not None,
        fail_message="Pipeline did not create portfolio_timeseries record for Day 2."
    )
    yield

# --- Test Function ---

def test_full_workflow_verification(setup_day2_workflow, db_engine, api_endpoints):
    """
    Performs a comprehensive verification of the database state and Performance API
    response after the Day 1 and Day 2 workflow is complete.
    """
    # --- ARRANGE ---
    query_url = api_endpoints["query"]

    # --- ACT & ASSERT: Database State ---
    with Session(db_engine) as session:
        # Day 1 Cash Position
        cash_r1 = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_1}).fetchone()
        assert cash_r1 and cash_r1.quantity == Decimal("1000000.0000000000")

        # Day 2 AAPL Position
        aapl_r2 = session.execute(text("SELECT quantity, cost_basis, market_value FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": AAPL_ID, "date": DAY_2}).fetchone()
        assert aapl_r2 and aapl_r2.quantity == Decimal("500.0000000000")
        assert aapl_r2.cost_basis == Decimal("88025.0000000000")
        assert aapl_r2.market_value == Decimal("89000.0000000000")

        # Day 2 Cash Position
        cash_r2 = session.execute(text("SELECT quantity FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"), {"pid": PORTFOLIO_ID, "sid": CASH_USD_ID, "date": DAY_2}).fetchone()
        assert cash_r2 and cash_r2.quantity == Decimal("911975.0000000000")

    # --- ACT & ASSERT: Performance API Response ---
    perf_payload = {
        "scope": { "as_of_date": DAY_2, "net_or_gross": "NET" },
        "periods": [{ "name": "YTD", "type": "YTD", "breakdown": "DAILY" }],
        "options": { "include_attributes": True, "include_cumulative": True, "include_annualized": True }
    }
    response = requests.post(f"{query_url}/portfolios/{PORTFOLIO_ID}/performance", json=perf_payload)
    assert response.status_code == 200, f"Performance API failed: {response.text}"
    perf_data = response.json()

    # Assert Summary
    summary_result = perf_data["summary"]["YTD"]
    assert "dailyReturn" not in summary_result
    assert pytest.approx(summary_result["cumulative_return"]) == 0.0975

    # Assert Breakdown
    breakdown_results = perf_data["breakdowns"]["YTD"]["results"]
    assert len(breakdown_results) == 2
    day2_breakdown = breakdown_results[1]
    assert "dailyReturn" in day2_breakdown
    assert "monthlyReturn" not in day2_breakdown
    assert pytest.approx(day2_breakdown["dailyReturn"]) == 0.0975