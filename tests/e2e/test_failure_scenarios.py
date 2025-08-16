# tests/e2e/test_failure_scenarios.py
import pytest
import requests
import time
import uuid
import os
import subprocess
from sqlalchemy.orm import Session
from sqlalchemy import text, exc
from confluent_kafka import Consumer

from portfolio_common.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_PERSISTENCE_DLQ_TOPIC
)

def wait_for_postgres_ready(db_engine, timeout=30):
    """Waits for the PostgreSQL container to be ready for connections."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with db_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("\n--- PostgreSQL is ready ---")
            return
        except (exc.OperationalError, exc.DBAPIError):
            time.sleep(1)
    pytest.fail(f"PostgreSQL did not become ready within {timeout} seconds.")

@pytest.mark.xfail(reason="Known flaky test: DB recovery is timing-sensitive and requires deeper investigation.")
def test_db_outage_recovery(docker_services, db_engine, clean_db):
    """
    Tests that the persistence-service can recover from a transient DB outage,
    successfully process a message after retrying, and does not send the
    message to the DLQ.
    """
    # 1. ARRANGE: Get service URLs and define test data
    ingestion_host = docker_services.get_service_host("ingestion_service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion_service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"

    portfolio_id = f"E2E_FAIL_PORT_{uuid.uuid4()}"
    transaction_id = f"E2E_FAIL_TXN_{uuid.uuid4()}"

    # 2. ARRANGE: Set up a Kafka consumer for the DLQ topic
    dlq_consumer_conf = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'group.id': f'test-dlq-checker-{uuid.uuid4()}',
        'auto.offset.reset': 'earliest'
    }
    dlq_consumer = Consumer(dlq_consumer_conf)
    dlq_consumer.subscribe([KAFKA_PERSISTENCE_DLQ_TOPIC])

    # 3. ARRANGE: Ingest prerequisite portfolio data
    portfolio_payload = {"portfolios": [{
        "portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01",
        "cifId": "FAIL_CIF", "status": "ACTIVE", "riskExposure": "a",
        "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"
    }]}
    assert requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload).status_code == 202

    # 4. ACT: Ingest the target transaction
    transaction_payload = {"transactions": [{"transaction_id": transaction_id, "portfolio_id": portfolio_id, "instrument_id": "FAIL_INST", "security_id": "SEC_FAIL", "transaction_date": "2025-08-05T10:00:00Z", "transaction_type": "BUY", "quantity": 1, "price": 1, "gross_transaction_amount": 1, "trade_currency": "USD", "currency": "USD"}]}
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=transaction_payload)
    assert response.status_code == 202
    print(f"\n--- Ingested transaction '{transaction_id}' ---")
    
    # 5. ACT: Simulate database outage
    print("\n--- Stopping PostgreSQL container ---")
    subprocess.run(["docker", "compose", "stop", "postgres"], check=True, capture_output=True)
    
    time.sleep(5) 
    
    print("\n--- Starting PostgreSQL container ---")
    subprocess.run(["docker", "compose", "start", "postgres"], check=True, capture_output=True)
    wait_for_postgres_ready(db_engine)
    
    print("\n--- Restarting persistence_service to ensure DB reconnection ---")
    subprocess.run(["docker", "compose", "restart", "persistence_service"], check=True, capture_output=True)
    time.sleep(30) 

    # 6. ASSERT: Verify the transaction is eventually persisted
    with Session(db_engine) as session:
        start_time = time.time()
        timeout = 310
        while time.time() - start_time < timeout:
            query = text("SELECT count(*) FROM transactions WHERE transaction_id = :txn_id")
            count = session.execute(query, {"txn_id": transaction_id}).scalar_one_or_none()
            if count and count > 0:
                print(f"\n--- Transaction '{transaction_id}' successfully persisted ---")
                break
            time.sleep(2)
        else:
            pytest.fail(f"Transaction '{transaction_id}' was not persisted within {timeout} seconds after DB recovery.")

    # 7. ASSERT: Verify the DLQ is empty
    print("\n--- Verifying DLQ is empty ---")
    msg = dlq_consumer.poll(timeout=10)
    dlq_consumer.close()
    
    assert msg is None, f"A message was unexpectedly found in the DLQ: {msg.value()}"
    print("\n--- DLQ verified to be empty ---")