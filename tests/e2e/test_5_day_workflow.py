# tests/e2e/test_5_day_workflow.py
import pytest
import requests
import time
from sqlalchemy.orm import Session
from sqlalchemy import text

# Constants for our test data
PORTFOLIO_ID = "E2E_WORKFLOW_01"
CASH_USD_ID = "CASH_USD"
CASH_EUR_ID = "CASH_EUR"
AAPL_ID = "SEC_AAPL_E2E"
IBM_ID = "SEC_IBM_E2E"

# Mark all tests in this file as being part of the 'dependency' group for ordering
pytestmark = pytest.mark.dependency()

@pytest.fixture(scope="module")
def setup_prerequisites(clean_db_module, api_endpoints):
    """
    A module-scoped fixture that ingests all prerequisite static data for the workflow:
    - The main portfolio.
    - All instruments used throughout the 5-day scenario.
    """
    ingestion_url = api_endpoints["ingestion"]

    # Ingest Portfolio [cite: 2012]
    portfolio_payload = {
      "portfolios": [
        {
          "portfolioId": PORTFOLIO_ID,
          "baseCurrency": "USD",
          "openDate": "2025-01-01",
          "cifId": "E2E_WF_CIF_01",
          "status": "ACTIVE",
          "riskExposure": "High",
          "investmentTimeHorizon": "Long",
          "portfolioType": "Discretionary",
          "bookingCenter": "SG"
        }
      ]
    }
    response = requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload, timeout=10)
    assert response.status_code == 202

    # Ingest Instruments [cite: 2013, 2014, 2015, 2016]
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

    # Allow a moment for the persistence service to process these events
    time.sleep(5)

    yield api_endpoints

def test_prerequisites_are_loaded(setup_prerequisites, db_engine):
    """
    Verifies that the portfolio and instruments from the setup fixture
    have been successfully persisted to the database. This acts as a
    gatekeeper for the rest of the tests in this file.
    """
    with Session(db_engine) as session:
        # Verify Portfolio
        portfolio_count = session.execute(text("SELECT count(*) FROM portfolios WHERE portfolio_id = :pid"), {"pid": PORTFOLIO_ID}).scalar()
        assert portfolio_count == 1, f"Portfolio {PORTFOLIO_ID} was not created."

        # Verify Instruments
        instrument_ids = [CASH_USD_ID, CASH_EUR_ID, AAPL_ID, IBM_ID]
        instrument_count = session.execute(text("SELECT count(*) FROM instruments WHERE security_id IN :ids"), {"ids": tuple(instrument_ids)}).scalar()
        assert instrument_count == 4, "Not all instruments were created."

@pytest.mark.dependency(depends=["test_prerequisites_are_loaded"])
def test_full_5_day_workflow():
    """
    This test will orchestrate the full 5-day workflow, including:
    1. Ingesting all prerequisite data (portfolios, instruments).
    2. Ingesting transactions and prices day-by-day.
    3. Polling for and verifying the state of positions and transactions at each stage.
    4. Ingesting back-dated data.
    5. Verifying the final, recalculated state of the portfolio.
    """
    pytest.skip("Test case for the full 5-day workflow is not yet implemented.")