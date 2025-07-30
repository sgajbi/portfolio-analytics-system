import pytest
import requests
import time
from decimal import Decimal

def test_full_valuation_pipeline(docker_services, db_connection, clean_db):
    """
    Tests the full pipeline from ingestion to position valuation, and verifies
    the final API response from the query service.
    """
    # 1. Define API endpoints
    ingestion_host = docker_services.get_service_host("ingestion-service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion-service", 8000)
    transactions_url = f"http://{ingestion_host}:{ingestion_port}/ingest/transactions"
    prices_url = f"http://{ingestion_host}:{ingestion_port}/ingest/market-prices"
    
    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)

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

    # 4. Poll the query-service API to verify the valuation result
    query_url = f"http://{query_host}:{query_port}/portfolios/{portfolio_id}/positions"
    start_time = time.time()
    timeout = 45
    while time.time() - start_time < timeout:
        try:
            api_response = requests.get(query_url)
            if api_response.status_code == 200:
                response_data = api_response.json()
                # Wait until the valuation object is populated
                if response_data["positions"] and response_data["positions"][0].get("valuation"):
                    break
        except requests.ConnectionError:
            pass # Service might not be ready yet
        time.sleep(2)
    else:
        pytest.fail(f"Position with valuation was not available via API within {timeout} seconds.")

    # 5. Assert the final API response
    assert len(response_data["positions"]) == 1
    position = response_data["positions"][0]
    valuation = position["valuation"]

    assert position["security_id"] == security_id
    assert position["quantity"] == "10.0000000000"
    assert position["cost_basis"] == "1000.0000000000"
    
    assert valuation["market_price"] == "110.0000000000"
    # Expected market_value = 10 * 110 = 1100
    assert valuation["market_value"] == "1100.0000000000"
    # Expected unrealized_gain_loss = 1100 - 1000 = 100
    assert valuation["unrealized_gain_loss"] == "100.0000000000"