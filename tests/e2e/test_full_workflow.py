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