# tests/e2e/test_cashflow_pipeline.py
import pytest
import requests
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

@pytest.fixture(scope="module")
def setup_cashflow_data(clean_db_module, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that ingests data for a simple cashflow scenario
    and waits for the calculation to be available via the query API.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]
    portfolio_id = "E2E_CASHFLOW_PORT_01"
    security_id = "SEC_CSHFLW"
    transaction_id = "E2E_CASHFLOW_BUY_01"

    # 1. Ingest prerequisite data (Portfolio and Instrument)
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG", "cifId": "CASHFLOW_CIF", "status": "Active"}]}
    instrument_payload = {"instruments": [{"securityId": security_id, "name": "Cashflow Test Stock", "isin": "CSHFLW123", "instrumentCurrency": "USD", "productType": "Equity"}]}
    requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload)
    requests.post(f"{ingestion_url}/ingest/instruments", json=instrument_payload)

    # 2. Define and ingest the transaction payload
    buy_payload = {"transactions": [{
        "transaction_id": transaction_id, "portfolio_id": portfolio_id, "instrument_id": "CSHFLW",
        "security_id": security_id, "transaction_date": "2025-07-28T00:00:00Z",
        "transaction_type": "BUY", "quantity": 10, "price": 100.0,
        "gross_transaction_amount": "1000.0", "trade_fee": "5.50",
        "trade_currency": "USD", "currency": "USD"
    }]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=buy_payload)

    # 3. Poll the query service to ensure the entire pipeline has completed
    poll_url = f"{query_url}/portfolios/{portfolio_id}/transactions"
    validation_func = lambda data: (
        data.get("transactions") and len(data["transactions"]) == 1 and
        data["transactions"][0].get("cashflow") is not None
    )
    poll_for_data(poll_url, validation_func, timeout=60)
    
    return {"transaction_id": transaction_id}


def test_cashflow_pipeline(setup_cashflow_data, db_engine):
    """
    Tests the full pipeline from ingestion to cashflow calculation by verifying
    the final state of the cashflow record in the database.
    """
    # ARRANGE
    transaction_id = setup_cashflow_data["transaction_id"]
    
    # ACT: The pipeline has already run; we just verify the final state in the DB.
    with Session(db_engine) as session:
        query = text("""
            SELECT amount, currency, classification, timing, level, calculation_type
            FROM cashflows WHERE transaction_id = :txn_id
        """)
        result = session.execute(query, {"txn_id": transaction_id}).fetchone()

    # ASSERT
    assert result is not None, f"Cashflow record for txn '{transaction_id}' not found."
    
    amount, currency, classification, timing, level, calc_type = result
    
    # Expected amount for a BUY is -(Gross Amount + Fee) = -(1000 + 5.50)
    expected_amount = -Decimal("1005.50")

    assert amount == expected_amount
    assert currency == "USD"
    assert classification == "INVESTMENT_OUTFLOW"
    assert timing == "EOD"
    assert level == "POSITION"
    assert calc_type == "NET"