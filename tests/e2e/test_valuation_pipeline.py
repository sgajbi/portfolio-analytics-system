import pytest
import requests
import time
import psycopg2
from testcontainers.compose import DockerCompose
from decimal import Decimal

def test_full_valuation_pipeline(docker_services: DockerCompose, db_connection):
    """
    Tests the full pipeline from ingestion to position valuation.
    """
    # 1. Define API endpoints
    host = docker_services.get_service_host("ingestion-service", 8000)
    port = docker_services.get_service_port("ingestion-service", 8000)
    transactions_url = f"http://{host}:{port}/ingest/transactions"
    prices_url = f"http://{host}:{port}/ingest/market-prices"

    # 2. Define payloads
    portfolio_id = "E2E_VAL_PORT_01"
    security_id = "SEC_E2E_VAL"
    tx_date = "2025-07-27"

    buy_payload = {"transactions": [{
        "transaction_id": "E2E_VAL_BUY_01", "portfolio_id": portfolio_id, 
        "instrument_id": "E2E_VAL", "security_id": security_id, 
        "transaction_date": tx_date, "transaction_type": "BUY", 
        "quantity": 10, "price": 100.0, "gross_transaction_amount": 1000.0, 
        "trade_currency": "USD", "currency": "USD"
    }]}
    
    price_payload = {"market_prices": [{
        "securityId": security_id, "priceDate": tx_date,
        "price": 110.0, "currency": "USD"
    }]}

    # 3. Post transaction and market price
    buy_response = requests.post(transactions_url, json=buy_payload)
    assert buy_response.status_code == 202
    
    price_response = requests.post(prices_url, json=price_payload)
    assert price_response.status_code == 202

    # 4. Poll the database to verify the valuation result
    with db_connection.cursor() as cursor:
        start_time = time.time()
        timeout = 45
        while time.time() - start_time < timeout:
            cursor.execute(
                "SELECT market_value, unrealized_gain_loss, cost_basis, quantity, market_price "
                "FROM position_history WHERE portfolio_id = %s AND security_id = %s",
                (portfolio_id, security_id)
            )
            result = cursor.fetchone()
            # Wait until the market_value field is populated
            if result and result[0] is not None:
                break
            time.sleep(1)
        else:
            pytest.fail(f"Position was not valued within {timeout} seconds. Last result: {result}")

    # 5. Assert the final state in the database
    market_value, unrealized_pl, cost_basis, quantity, market_price = result
    
    assert quantity == Decimal("10.0000000000")
    assert cost_basis == Decimal("1000.0000000000")
    assert market_price == Decimal("110.0000000000")
    
    # Expected market_value = quantity * market_price = 10 * 110 = 1100
    assert market_value == Decimal("1100.0000000000")
    
    # Expected unrealized_pl = market_value - cost_basis = 1100 - 1000 = 100
    assert unrealized_pl == Decimal("100.0000000000")