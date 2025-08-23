# tests/e2e/test_5_day_workflow.py
import pytest
import requests
import time
from sqlalchemy.orm import Session
from sqlalchemy import text, Engine
from decimal import Decimal
from typing import Callable, Any

# Constants for our test data
PORTFOLIO_ID = "E2E_WORKFLOW_01"
CASH_USD_ID = "CASH_USD"
CASH_EUR_ID = "CASH_EUR"
AAPL_ID = "SEC_AAPL_E2E"
IBM_ID = "SEC_IBM_E2E"

DAY_1 = "2025-08-19"
DAY_2 = "2025-08-20"
DAY_3 = "2025-08-21"
DAY_4 = "2025-08-22"
DAY_5 = "2025-08-23"

# Mark all tests in this file as being part of the 'dependency' group for ordering
pytestmark = pytest.mark.dependency()

def poll_db_until(
    db_engine: Engine,
    query: str,
    validation_func: Callable[[Any], bool],
    params: dict = {},
    timeout: int = 60,
    interval: int = 2,
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
    
    pytest.fail(
        f"Polling timed out after {timeout} seconds. Last result: {last_result}"
    )


@pytest.fixture(scope="module")
def setup_prerequisites(clean_db_module, api_endpoints):
    """
    A module-scoped fixture that ingests all prerequisite static data for the workflow.
    """
    ingestion_url = api_endpoints["ingestion"]

    # Ingest Portfolio
    portfolio_payload = {
      "portfolios": [
        {
          "portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01",
          "cifId": "E2E_WF_CIF_01", "status": "ACTIVE", "riskExposure": "High",
          "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG"
        }
      ]
    }
    response = requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload, timeout=10)
    assert response.status_code == 202

    # Ingest Instruments
    instruments_payload = {
        "instruments": [
            {"securityId": CASH_USD_ID, "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash"},
            {"securityId": CASH_EUR_ID, "name": "Euro", "isin": "CASH_EUR_ISIN", "instrumentCurrency": "EUR", "productType": "Cash"},
            {"securityId": AAPL_ID, "name": "Apple Inc.", "isin": "US0378331005_E2E", "instrumentCurrency": "USD", "productType": "Equity"},
            {"securityId": IBM_ID, "name": "IBM Corp.", "isin": "US4592001014_E2E", "instrumentCurrency": "USD", "productType": "Equity"}
        ]
    }
    response = requests.post(f"{ingestion_url}/ingest/instruments", json=instruments_payload, timeout=10)
    assert response.status_code == 202
    
    time.sleep(5)
    yield api_endpoints

def test_prerequisites_are_loaded(setup_prerequisites, db_engine):
    """
    Verifies that the portfolio and instruments from the setup fixture
    have been successfully persisted to the database.
    """
    with Session(db_engine) as session:
        portfolio_count = session.execute(text("SELECT count(*) FROM portfolios WHERE portfolio_id = :pid"), {"pid": PORTFOLIO_ID}).scalar()
        assert portfolio_count == 1, f"Portfolio {PORTFOLIO_ID} was not created."

        instrument_ids = [CASH_USD_ID, CASH_EUR_ID, AAPL_ID, IBM_ID]
        instrument_count = session.execute(text("SELECT count(*) FROM instruments WHERE security_id IN :ids"), {"ids": tuple(instrument_ids)}).scalar()
        assert instrument_count == 4, "Not all instruments were created."

@pytest.mark.dependency(depends=["test_prerequisites_are_loaded"])
def test_day_1_workflow(setup_prerequisites, db_engine):
    """
    Tests Day 1: Ingests a business date, a deposit, and a cash price,
    then verifies the final state of the daily snapshot.
    """
    # ARRANGE
    ingestion_url = setup_prerequisites["ingestion"]

    # ACT: Ingest all data for Day 1
    requests.post(f"{ingestion_url}/ingest/business-dates", json={"business_dates": [{"businessDate": DAY_1}]})
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": "TXN_DAY1_DEPOSIT_01", "portfolio_id": PORTFOLIO_ID, "security_id": CASH_USD_ID, "instrument_id": "CASH_USD", "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1.0, "gross_transaction_amount": 1000000.0, "trade_currency": "USD", "currency": "USD"}]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": CASH_USD_ID, "priceDate": DAY_1, "price": 1.0, "currency": "USD"}]})
    
    # ASSERT: Poll the database until the snapshot is fully valued
    query = """
        SELECT quantity, cost_basis, market_value, unrealized_gain_loss, valuation_status
        FROM daily_position_snapshots
        WHERE portfolio_id = :portfolio_id AND security_id = :security_id AND date = :date
    """
    params = {"portfolio_id": PORTFOLIO_ID, "security_id": CASH_USD_ID, "date": DAY_1}
    
    def validation_func(result):
        return result is not None and result.valuation_status == 'VALUED_CURRENT'

    poll_db_until(db_engine, query, validation_func, params)

@pytest.mark.dependency(depends=["test_day_1_workflow"])
def test_day_2_workflow(setup_prerequisites, db_engine):
    """
    Tests Day 2: Ingests a stock purchase and verifies the final state
    of the portfolio time series.
    """
    # ARRANGE
    ingestion_url = setup_prerequisites["ingestion"]

    # ACT: Ingest all data for Day 2
    requests.post(f"{ingestion_url}/ingest/business-dates", json={"business_dates": [{"businessDate": DAY_2}]})
    transactions_payload = { "transactions": [
        {"transaction_id": "TXN_DAY2_BUY_AAPL_01", "portfolio_id": PORTFOLIO_ID, "security_id": AAPL_ID, "instrument_id": "AAPL", "transaction_date": f"{DAY_2}T11:00:00Z", "transaction_type": "BUY", "quantity": 1000, "price": 175.0, "gross_transaction_amount": 175000.0, "trade_fee": 25.50, "trade_currency": "USD", "currency": "USD" },
        {"transaction_id": "TXN_DAY2_CASH_SETTLE_01", "portfolio_id": PORTFOLIO_ID, "security_id": CASH_USD_ID, "instrument_id": "CASH_USD", "transaction_date": f"{DAY_2}T11:00:00Z", "transaction_type": "SELL", "quantity": 175025.50, "price": 1.0, "gross_transaction_amount": 175025.50, "trade_currency": "USD", "currency": "USD"}
    ]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=transactions_payload)
    prices_payload = {"market_prices": [
        {"securityId": AAPL_ID, "priceDate": DAY_2, "price": 178.0, "currency": "USD"},
        {"securityId": CASH_USD_ID, "priceDate": DAY_2, "price": 1.0, "currency": "USD"}
    ]}
    requests.post(f"{ingestion_url}/ingest/market-prices", json=prices_payload)

    # ASSERT: Poll the database until the portfolio timeseries for Day 2 is correct
    query = """
        SELECT bod_market_value, eod_market_value, bod_cashflow, eod_cashflow, fees
        FROM portfolio_timeseries
        WHERE portfolio_id = :portfolio_id AND date = :date
    """
    params = {"portfolio_id": PORTFOLIO_ID, "date": DAY_2}
    
    # Expected EOD MV = (1M - 175025.50) cash + (1000 * 178) aapl = 824974.50 + 178000 = 1002974.50
    expected_eod_mv = Decimal("1002974.50")

    def validation_func(result):
        return result is not None and result.eod_market_value == expected_eod_mv

    poll_db_until(db_engine, query, validation_func, params, timeout=90)