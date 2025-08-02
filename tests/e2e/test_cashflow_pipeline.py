import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

def test_cashflow_pipeline(docker_services, db_engine, clean_db):
    """
    Tests the full pipeline from ingestion to cashflow calculation.
    It ingests a BUY transaction and verifies that a corresponding
    cashflow record is created correctly in the database.
    """
    # 1. Get the API endpoint from the running docker-compose stack
    host = docker_services.get_service_host("ingestion-service", 8000)
    port = docker_services.get_service_port("ingestion-service", 8000)
    api_url = f"http://{host}:{port}/ingest/transactions"

    # 2. Define a test transaction payload
    portfolio_id = "E2E_CASHFLOW_PORT_01"
    transaction_id = "E2E_CASHFLOW_BUY_01"
    gross_amount = Decimal("1000.0")
    fee = Decimal("5.50")

    buy_payload = { "transactions": [{
        "transaction_id": transaction_id, 
        "portfolio_id": portfolio_id, 
        "instrument_id": "CSHFLW", 
        "security_id": "SEC_CSHFLW", 
        "transaction_date": "2025-07-28T00:00:00Z", 
        "transaction_type": "BUY", 
        "quantity": 10, 
        "price": 100.0, 
        "gross_transaction_amount": str(gross_amount),
        "trade_fee": str(fee),
        "trade_currency": "USD", 
        "currency": "USD"
    }]}

    # 3. Post the transaction to the ingestion service
    response = requests.post(api_url, json=buy_payload)
    assert response.status_code == 202

    # 4. Poll the cashflows table to verify the result
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

    # 5. Assert the final state in the database
    amount, currency, classification, timing, level, calc_type = result

    # Expected amount for a BUY is -(gross_amount + fee)
    expected_amount = -(gross_amount + fee)

    assert amount == expected_amount
    assert currency == "USD"
    assert classification == "INVESTMENT_OUTFLOW"
    assert timing == "EOD"
    assert level == "POSITION"
    assert calc_type == "NET"