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

@pytest.fixture(scope="module")
def setup_workflow_data(clean_db_module, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that sets up the initial state for the full workflow test.
    This fixture now ingests the portfolio, instruments, and their initial market prices.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]

    # --- 1. Ingest Portfolio ---
    portfolio_payload = {
        "portfolios": [{
            "portfolioId": PORTFOLIO_ID,
            "baseCurrency": BASE_CURRENCY,
            "openDate": "2025-01-01",
            "cifId": "WF_CIF_01",
            "status": "ACTIVE",
            "riskExposure": "High",
            "investmentTimeHorizon": "Long",
            "portfolioType": "Discretionary",
            "bookingCenter": "SG"
        }]
    }
    response = requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload)
    assert response.status_code == 202, f"Failed to ingest portfolio: {response.text}"

    # --- 2. Ingest Instruments (Cash and Equities) ---
    instruments_payload = {
        "instruments": [
            {"securityId": CASH_USD_ID, "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash"},
            {"securityId": CASH_EUR_ID, "name": "Euro", "isin": "CASH_EUR_ISIN", "instrumentCurrency": "EUR", "productType": "Cash"},
            {"securityId": AAPL_ID, "name": "Apple Inc.", "isin": "US0378331005", "instrumentCurrency": "USD", "productType": "Equity"},
            {"securityId": IBM_ID, "name": "IBM Corp.", "isin": "US4592001014", "instrumentCurrency": "USD", "productType": "Equity"}
        ]
    }
    response = requests.post(f"{ingestion_url}/ingest/instruments", json=instruments_payload)
    assert response.status_code == 202, f"Failed to ingest instruments: {response.text}"

    # --- 3. Ingest Market Prices ---
    prices_payload = {
        "market_prices": [
            {"securityId": CASH_USD_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "USD"},
            {"securityId": CASH_EUR_ID, "priceDate": "2025-08-18", "price": 1.0, "currency": "EUR"},
            {"securityId": AAPL_ID, "priceDate": "2025-08-18", "price": 175.0, "currency": "USD"},
            {"securityId": IBM_ID, "priceDate": "2025-08-18", "price": 150.0, "currency": "USD"}
        ]
    }
    response = requests.post(f"{ingestion_url}/ingest/market-prices", json=prices_payload)
    assert response.status_code == 202, f"Failed to ingest prices: {response.text}"

    # --- 4. Poll to verify persistence ---
    # Poll for the portfolio
    poll_for_data(
        f"{query_url}/portfolios/{PORTFOLIO_ID}",
        lambda data: data and data.get("portfolio_id") == PORTFOLIO_ID,
        timeout=60
    )
    # Poll for the last price to ensure all are likely persisted
    poll_for_data(
        f"{query_url}/prices?security_id={IBM_ID}",
        lambda data: (
            data and data.get("prices") and
            # FIX: Compare as Decimals to handle varying precision
            Decimal(data["prices"][0]["price"]) == Decimal("150.0")
        ),
        timeout=60
    )
    
    time.sleep(2)

    yield {
        "ingestion_url": ingestion_url,
        "query_url": query_url
    }

def test_workflow_step1_portfolio_and_instrument_creation(setup_workflow_data, db_engine):
    """
    Verifies that the portfolio and instruments were created correctly in the database.
    """
    # ARRANGE
    expected_instrument_ids = {CASH_USD_ID, CASH_EUR_ID, AAPL_ID, IBM_ID}

    with Session(db_engine) as session:
        # ACT
        portfolio_query = text("SELECT portfolio_id, base_currency, status FROM portfolios WHERE portfolio_id = :pid")
        portfolio_result = session.execute(portfolio_query, {"pid": PORTFOLIO_ID}).fetchone()
        
        instrument_query = text("SELECT security_id FROM instruments WHERE security_id = ANY(:ids)")
        instrument_results = session.execute(instrument_query, {"ids": list(expected_instrument_ids)}).fetchall()
        
    # ASSERT
    assert portfolio_result is not None, f"Portfolio {PORTFOLIO_ID} not found."
    assert portfolio_result.portfolio_id == PORTFOLIO_ID
    
    persisted_instrument_ids = {row[0] for row in instrument_results}
    assert persisted_instrument_ids == expected_instrument_ids, "Mismatch in persisted instruments."

def test_workflow_step2_price_setup(setup_workflow_data, db_engine):
    """
    Verifies that the market prices were created correctly in the database.
    """
    # ARRANGE
    price_date = "2025-08-18"
    
    with Session(db_engine) as session:
        # ACT
        price_query = text("SELECT security_id, price FROM market_prices WHERE price_date = :p_date")
        price_results = session.execute(price_query, {"p_date": price_date}).fetchall()

    # ASSERT
    assert len(price_results) == 4, "Expected 4 price records for the given date."
    
    prices_map = {row[0]: row[1] for row in price_results}
    
    assert prices_map[CASH_USD_ID] == Decimal("1.0000000000")
    assert prices_map[AAPL_ID] == Decimal("175.0000000000")
    assert prices_map[IBM_ID] == Decimal("150.0000000000")