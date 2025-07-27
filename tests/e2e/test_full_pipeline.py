import pytest
import requests
import time
import psycopg2
from testcontainers.compose import DockerCompose
from decimal import Decimal

def test_full_pipeline(docker_services: DockerCompose, db_connection):
    """
    Tests the full pipeline from ingestion to cost calculation.
    """
    # 1. Get the API endpoint
    host = docker_services.get_service_host("ingestion-service", 8000)
    port = docker_services.get_service_port("ingestion-service", 8000)
    api_url = f"http://{host}:{port}/ingest/transactions"

    # 2. Define transaction payloads
    portfolio_id = "E2E_TEST_PORT_01"
    buy_payload = { "transactions": [{
        "transaction_id": "E2E_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "APPL", 
        "security_id": "SEC_APPL", "transaction_date": "2025-01-10", "transaction_type": "BUY", 
        "quantity": 10, "price": 150.0, "gross_transaction_amount": 1500.0, 
        "trade_currency": "USD", "currency": "USD"
    }]}
    sell_payload = { "transactions": [{
        "transaction_id": "E2E_SELL_01", "portfolio_id": portfolio_id, "instrument_id": "APPL", 
        "security_id": "SEC_APPL", "transaction_date": "2025-01-20", "transaction_type": "SELL", 
        "quantity": 10, "price": 175.0, "gross_transaction_amount": 1750.0, 
        "trade_currency": "USD", "currency": "USD"
    }]}

    # 3. Post transactions to the ingestion service
    buy_response = requests.post(api_url, json=buy_payload)
    assert buy_response.status_code == 202
    
    sell_response = requests.post(api_url, json=sell_payload)
    assert sell_response.status_code == 202

    # 4. Poll the database to verify the results
    with db_connection.cursor() as cursor:
        start_time = time.time()
        timeout = 30
        while time.time() - start_time < timeout:
            cursor.execute(
                "SELECT transaction_id, transaction_type, net_cost, realized_gain_loss "
                "FROM transactions WHERE portfolio_id = %s ORDER BY transaction_date",
                (portfolio_id,)
            )
            results = cursor.fetchall()
            # Wait until both transactions are processed and the SELL has a gain/loss
            if len(results) == 2 and results[1][3] is not None:
                break
            time.sleep(1)
        else:
            pytest.fail(f"Transactions were not processed within {timeout} seconds. Results: {results}")

    # 5. Assert the final state in the database
    buy_record = results[0]
    sell_record = results[1]

    # BUY transaction checks
    assert buy_record[0] == "E2E_BUY_01"
    assert buy_record[1] == "BUY"
    assert buy_record[2] == Decimal("1500.0000000000") # net_cost
    assert buy_record[3] is None # realized_gain_loss

    # SELL transaction checks
    assert sell_record[0] == "E2E_SELL_01"
    assert sell_record[1] == "SELL"
    assert sell_record[2] == Decimal("-1500.0000000000") # net_cost (cost of shares sold)
    assert sell_record[3] == Decimal("250.0000000000") # realized_gain_loss (1750 - 1500)