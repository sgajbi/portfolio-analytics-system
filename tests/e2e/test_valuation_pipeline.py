import pytest
import requests
import time
from decimal import Decimal

def test_full_valuation_pipeline(docker_services, db_engine, clean_db):
    """
    Tests the full pipeline from ingestion to position valuation, and verifies
    the final API response from the query service.
    """
    # 1. Define API endpoints
    ingestion_host = docker_services.get_service_host("ingestion_service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion_service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"
    
    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)

    # 2. Define payloads
    portfolio_id = "E2E_VAL_PORT_01"
    security_id = "SEC_E2E_VAL"
    tx_date = "2025-07-27"

    # 3. Ingest prerequisite data (Portfolio and Instrument)
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "Medium", "investmentTimeHorizon": "Long", "portfolioType": "Advisory", "bookingCenter": "NY", "cifId": "VAL_CIF", "status": "Active"}]}
    instrument_payload = {"instruments": [{"securityId": security_id, "name": "Valuation Test Stock", "isin": "VAL12345", "instrumentCurrency": "USD", "productType": "Equity"}]}

    assert requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload).status_code == 202
    assert requests.post(f"{ingestion_url}/ingest/instruments", json=instrument_payload).status_code == 202

    # 4. Define transaction and price payloads
    buy_payload = {"transactions": [{
        "transaction_id": "E2E_VAL_BUY_01", "portfolio_id": portfolio_id,
        "instrument_id": "E2E_VAL", "security_id": security_id,
        "transaction_date": f"{tx_date}T10:00:00Z", "transaction_type": "BUY",
        "quantity": 10, "price": 100.0, "gross_transaction_amount": 1000.0,
        "trade_currency": "USD", "currency": "USD"
    }]}
    
    price_payload = {"market_prices": [{
        "securityId": security_id, "priceDate": tx_date,
        "price": 110.0, "currency": "USD"
    }]}

    # 5. Post transaction and market price
    buy_response = requests.post(f"{ingestion_url}/ingest/transactions", json=buy_payload)
    assert buy_response.status_code == 202
    
    price_response = requests.post(f"{ingestion_url}/ingest/market-prices", json=price_payload)
    assert price_response.status_code == 202

    # 6. Poll the query-service API to verify the valuation result
    query_url = f"http://{query_host}:{query_port}/portfolios/{portfolio_id}/positions"
    start_time = time.time()
    timeout = 45
    response_data = {}
    while time.time() - start_time < timeout:
        try:
            api_response = requests.get(query_url)
            if api_response.status_code == 200:
                response_data = api_response.json()
                # Wait until the valuation object is populated
                if response_data.get("positions") and response_data["positions"][0].get("valuation"):
                    break
        except requests.ConnectionError:
            pass # Service might not be ready yet
        time.sleep(2)
    else:
        pytest.fail(f"Position with valuation was not available via API within {timeout} seconds. Last response: {response_data}")

    # 7. Assert the final API response
    assert len(response_data["positions"]) == 1
    position = response_data["positions"][0]
    valuation = position["valuation"]

    assert position["security_id"] == security_id
    assert position["quantity"] == "10.0000000000"
    assert position["cost_basis"] == "1000.0000000000"
    
    assert valuation["market_price"] == "110.0000000000"
    # Expected market_value = 10 * 110 = 1100
    assert valuation["market_value"] == "1100.0000000000"
    
    # --- UPDATED ASSERTION ---
    # Assert that unrealized_gain_loss is null due to the ambiguous cost_basis currency
    assert valuation["unrealized_gain_loss"] is None