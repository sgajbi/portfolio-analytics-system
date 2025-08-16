# tests/e2e/test_valuation_pipeline.py
import pytest
import requests
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session

@pytest.fixture(scope="module")
def setup_valuation_data(clean_db_module, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that ingests data for a simple valuation scenario,
    and waits for the calculation to be available via the query API.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]
    portfolio_id = "E2E_VAL_PORT_01"
    security_id = "SEC_E2E_VAL"
    tx_date = "2025-07-27"

    # 1. Ingest prerequisite data
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "Medium", "investmentTimeHorizon": "Long", "portfolioType": "Advisory", "bookingCenter": "NY", "cifId": "VAL_CIF", "status": "Active"}]}
    instrument_payload = {"instruments": [{"securityId": security_id, "name": "Valuation Test Stock", "isin": "VAL12345", "instrumentCurrency": "USD", "productType": "Equity"}]}
    requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload)
    requests.post(f"{ingestion_url}/ingest/instruments", json=instrument_payload)

    # 2. Ingest transaction and market price
    buy_payload = {"transactions": [{"transaction_id": "E2E_VAL_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "E2E_VAL", "security_id": security_id, "transaction_date": f"{tx_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 100.0, "gross_transaction_amount": 1000.0, "trade_currency": "USD", "currency": "USD"}]}
    price_payload = {"market_prices": [{"securityId": security_id, "priceDate": tx_date, "price": 110.0, "currency": "USD"}]}
    requests.post(f"{ingestion_url}/ingest/transactions", json=buy_payload)
    requests.post(f"{ingestion_url}/ingest/market-prices", json=price_payload)

    # 3. Poll until the final position is valued, ensuring the pipeline has completed
    poll_url = f"{query_url}/portfolios/{portfolio_id}/positions"
    validation_func = lambda data: (
        data.get("positions") and len(data["positions"]) == 1 and
        data["positions"][0].get("valuation", {}).get("unrealized_gain_loss") is not None
    )
    poll_for_data(poll_url, validation_func, timeout=60)

    return {"portfolio_id": portfolio_id, "query_url": query_url}


def test_full_valuation_pipeline(setup_valuation_data):
    """
    Tests the full pipeline from ingestion to position valuation, and verifies
    the final API response from the query service.
    """
    # ARRANGE
    portfolio_id = setup_valuation_data["portfolio_id"]
    query_url = setup_valuation_data["query_url"]
    
    # ACT: The pipeline has already run; we just query the final state.
    api_response = requests.get(f"{query_url}/portfolios/{portfolio_id}/positions")
    assert api_response.status_code == 200
    response_data = api_response.json()

    # ASSERT
    assert len(response_data["positions"]) == 1
    position = response_data["positions"][0]
    valuation = position["valuation"]

    assert position["security_id"] == "SEC_E2E_VAL"
    assert position["quantity"] == "10.0000000000"
    assert position["cost_basis"] == "1000.0000000000"
    
    assert valuation["market_price"] == "110.0000000000"
    # Expected market_value = 10 shares * 110/share = 1100
    assert valuation["market_value"] == "1100.0000000000"
    
    # Expected unrealized_gain_loss = 1100 (MV) - 1000 (Cost) = 100
    assert Decimal(valuation["unrealized_gain_loss"]).quantize(Decimal("0.01")) == Decimal("100.00")