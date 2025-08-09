import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

def test_cashflow_pipeline(docker_services, db_engine, clean_db):
    """
    Tests the full pipeline from ingestion to cashflow calculation.
    It ingests a portfolio, an instrument, and a BUY transaction, then
    verifies that a corresponding cashflow record is created correctly.
    """
    # 1. Get the API endpoints from the running docker-compose stack
    host = docker_services.get_service_host("ingestion_service", 8000)
    port = docker_services.get_service_port("ingestion_service", 8000)
    portfolio_url = f"http://{host}:{port}/ingest/portfolios"
    instrument_url = f"http://{host}:{port}/ingest/instruments"
    transaction_url = f"http://{host}:{port}/ingest/transactions"

    # 2. Define test data
    portfolio_id = "E2E_CASHFLOW_PORT_01"
    security_id = "SEC_CSHFLW"
    transaction_id = "E2E_CASHFLOW_BUY_01"
    gross_amount = Decimal("1000.0")
    fee = Decimal("5.50")

    # 3. Ingest prerequisite data (Portfolio and Instrument)
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "High", "investmentTimeHorizon": "Long", "portfolioType": "Discretionary", "bookingCenter": "SG", "cifId": "CASHFLOW_CIF", "status": "Active"}]}
    instrument_payload = {"instruments": [{"securityId": security_id, "name": "Cashflow Test Stock", "isin": "CSHFLW123", "instrumentCurrency": "USD", "productType": "Equity"}]}

    assert requests.post(portfolio_url, json=portfolio_payload).status_code == 202
    assert requests.post(instrument_url, json=instrument_payload).status_code == 202

    # 4. Define and ingest the transaction payload
    buy_payload = { "transactions": [{
        "transaction_id": transaction_id,
        "portfolio_id": portfolio_id,
        "instrument_id": "CSHFLW",
        "security_id": security_id,
        "transaction_date": "2025-07-28T00:00:00Z",
        "transaction_type": "BUY",
        "quantity": 10,
        "price": 100.0,
        "gross_transaction_amount": str(gross_amount),
        "trade_fee": str(fee),
        "trade_currency": "USD",
        "currency": "USD"
    }]}

    response = requests.post(transaction_url, json=buy_payload)
    assert response.status_code == 202

    # 5. Poll the cashflows table to verify the result
    with Session(db_engine) as session:
        start_time = time.time()
        timeout = 45 # seconds
        while time.time() - start_time < timeout:
            query = text("""
                SELECT amount, currency, classification, timing, level, calculation_type
                FROM cashflows WHERE transaction_id = :txn_id
            """)
            result = session.execute(query, {"txn_id": transaction_id}).fetchone()
            if result:
                break
            time.sleep(1)
        else:
            pytest.fail(f"Cashflow record for txn '{transaction_id}' not found within {timeout} seconds.")

    # 6. Assert the final state in the database
    amount, currency, classification, timing, level, calc_type = result

    # Expected amount for a BUY is -(gross_amount + fee)
    expected_amount = -(gross_amount + fee)

    assert amount == expected_amount
    assert currency == "USD"
    assert classification == "INVESTMENT_OUTFLOW"
    assert timing == "EOD"
    assert level == "POSITION"
    assert calc_type == "NET"