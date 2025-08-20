# tests/e2e/test_full_workflow.py
import pytest
import requests
import time
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date

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
    This first step ingests the portfolio and all required instruments.
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

    # --- 3. Poll to verify persistence ---
    # Poll for the portfolio
    poll_for_data(
        f"{query_url}/portfolios/{PORTFOLIO_ID}",
        lambda data: data and data.get("portfolio_id") == PORTFOLIO_ID,
        timeout=60
    )
    # Poll for the last instrument to ensure all are likely persisted
    poll_for_data(
        f"{query_url}/instruments?security_id={IBM_ID}",
        lambda data: data and data.get("instruments") and data["instruments"][0]["security_id"] == IBM_ID,
        timeout=60
    )
    
    # Give a brief moment for the DB to be fully consistent after the last poll
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
        # ACT: Query the database directly for the created entities
        
        # Verify Portfolio
        portfolio_query = text("SELECT portfolio_id, base_currency, status FROM portfolios WHERE portfolio_id = :pid")
        portfolio_result = session.execute(portfolio_query, {"pid": PORTFOLIO_ID}).fetchone()
        
        # Verify Instruments
        instrument_query = text("SELECT security_id FROM instruments WHERE security_id = ANY(:ids)")
        instrument_results = session.execute(instrument_query, {"ids": list(expected_instrument_ids)}).fetchall()
        
    # ASSERT
    # Portfolio Assertions
    assert portfolio_result is not None, f"Portfolio {PORTFOLIO_ID} not found in the database."
    assert portfolio_result.portfolio_id == PORTFOLIO_ID
    assert portfolio_result.base_currency == BASE_CURRENCY
    assert portfolio_result.status == "ACTIVE"
    
    # Instrument Assertions
    persisted_instrument_ids = {row[0] for row in instrument_results}
    assert persisted_instrument_ids == expected_instrument_ids, "Mismatch in persisted instruments."