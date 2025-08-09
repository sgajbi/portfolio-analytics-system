import pytest
import requests
import time
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import text

def test_transaction_ingestion_is_idempotent(docker_services, db_engine, clean_db):
    """
    Tests that the entire persistence pipeline is idempotent for transactions.
    It ingests the exact same transaction twice and verifies that only one
    record is created in the database.
    """
    # 1. Get API endpoints
    ingestion_host = docker_services.get_service_host("ingestion_service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion_service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"

    # 2. Define unique IDs for this test run
    portfolio_id = f"E2E_IDEMPOTENT_PORT_{uuid.uuid4()}"
    transaction_id = f"E2E_IDEMPOTENT_TXN_{uuid.uuid4()}"

    # 3. Ingest prerequisite portfolio data to satisfy FK constraints
    portfolio_payload = {"portfolios": [{
        "portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01",
        "cifId": "IDEMPOTENT_CIF", "status": "ACTIVE", "riskExposure": "a",
        "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"
    }]}
    assert requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload).status_code == 202

    # 4. Define the transaction payload that will be sent twice
    transaction_payload = {"transactions": [{
        "transaction_id": transaction_id,
        "portfolio_id": portfolio_id,
        "instrument_id": "IDEMPOTENT_INST",
        "security_id": "SEC_IDEMPOTENT",
        "transaction_date": "2025-08-05T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": 1, "price": 1, "gross_transaction_amount": 1,
        "trade_currency": "USD", "currency": "USD"
    }]}

    # 5. ACT: Post the same payload twice in quick succession
    response1 = requests.post(f"{ingestion_url}/ingest/transactions", json=transaction_payload)
    assert response1.status_code == 202

    response2 = requests.post(f"{ingestion_url}/ingest/transactions", json=transaction_payload)
    assert response2.status_code == 202

    # 6. ASSERT: Poll the database to verify the final state
    # We give the system ample time to process both messages.
    # If the logic is faulty, a second record would appear, causing the count to become 2.
    time.sleep(15) # Allow time for both messages to be consumed

    with Session(db_engine) as session:
        # Check that exactly one transaction record was created
        query_txn = text("SELECT count(*) FROM transactions WHERE transaction_id = :txn_id")
        transaction_count = session.execute(query_txn, {"txn_id": transaction_id}).scalar_one()
        assert transaction_count == 1, "Duplicate transaction was created"

        # Check that exactly one 'processed_event' record was created for this consumer
        query_events = text("""
            SELECT count(*) FROM processed_events 
            WHERE portfolio_id = :portfolio_id AND service_name = 'persistence-transactions'
        """)
        processed_event_count = session.execute(query_events, {"portfolio_id": portfolio_id}).scalar_one()
        assert processed_event_count == 1, "Duplicate processed_event record was created"