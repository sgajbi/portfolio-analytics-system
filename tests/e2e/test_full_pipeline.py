import pytest
import requests
import time
import psycopg2
from testcontainers.compose import DockerCompose
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

def test_full_pipeline(docker_services: DockerCompose, db_engine, clean_db):
    """
    Tests the full pipeline from ingestion to cost calculation and
    verifies the final API response from the query service.
    """
    # 1. Get API endpoints
    ingestion_host = docker_services.get_service_host("ingestion-service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion-service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}/ingest/transactions"

    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)
    
    # 2. Define transaction payloads
    portfolio_id = "E2E_TEST_PORT_01"
    buy_payload = { "transactions": [{
        "transaction_id": "E2E_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "APPL", 
        "security_id": "SEC_APPL", "transaction_date": "2025-01-10T00:00:00Z", "transaction_type": "BUY", 
        "quantity": 10, "price": 150.0, "gross_transaction_amount": 1500.0, 
        "trade_currency": "USD", "currency": "USD"
    }]}
    sell_payload = { "transactions": [{
        "transaction_id": "E2E_SELL_01", "portfolio_id": portfolio_id, "instrument_id": "APPL", 
        "security_id": "SEC_APPL", "transaction_date": "2025-01-20T00:00:00Z", "transaction_type": "SELL", 
        "quantity": 10, "price": 175.0, "gross_transaction_amount": 1750.0, 
        "trade_currency": "USD", "currency": "USD"
    }]}

    # 3. Post transactions to the ingestion service
    buy_response = requests.post(ingestion_url, json=buy_payload)
    assert buy_response.status_code == 202
    
    sell_response = requests.post(ingestion_url, json=sell_payload)
    assert sell_response.status_code == 202

    # 4. Poll the database to verify the processing is complete
    with Session(db_engine) as session:
        start_time = time.time()
        timeout = 60
        while time.time() - start_time < timeout:
            query = text("SELECT t.transaction_id FROM transactions t JOIN cashflows c ON t.transaction_id = c.transaction_id WHERE t.portfolio_id = :portfolio_id")
            results = session.execute(query, {"portfolio_id": portfolio_id}).fetchall()
            # Wait until both transactions have been processed by all calculators
            if len(results) == 2:
                break
            time.sleep(2)
        else:
            pytest.fail(f"Transactions were not fully processed within {timeout} seconds.")

    # 5. Query the API to verify the final response
    query_url = f"http://{query_host}:{query_port}/portfolios/{portfolio_id}/transactions"
    api_response = requests.get(query_url)
    assert api_response.status_code == 200
    response_data = api_response.json()

    # 6. Assert the API response structure and content
    assert response_data["portfolio_id"] == portfolio_id
    assert response_data["total"] == 2
    assert len(response_data["transactions"]) == 2

    # Transactions are ordered by date descending
    sell_txn_data = response_data["transactions"][0]
    buy_txn_data = response_data["transactions"][1]

    # SELL transaction checks
    assert sell_txn_data["transaction_id"] == "E2E_SELL_01"
    assert "cashflow" in sell_txn_data
    assert sell_txn_data["cashflow"]["amount"] == "1750.0000000000"
    assert sell_txn_data["cashflow"]["classification"] == "INVESTMENT_INFLOW"
    assert sell_txn_data["cashflow"]["level"] == "POSITION"

    # BUY transaction checks
    assert buy_txn_data["transaction_id"] == "E2E_BUY_01"
    assert "cashflow" in buy_txn_data
    assert buy_txn_data["cashflow"]["amount"] == "-1500.0000000000"
    assert buy_txn_data["cashflow"]["classification"] == "INVESTMENT_OUTFLOW"
    assert buy_txn_data["cashflow"]["level"] == "POSITION"