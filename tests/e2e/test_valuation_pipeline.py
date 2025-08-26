# tests/e2e/test_valuation_pipeline.py
import pytest
import requests
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Callable, Any

# The poll_db_until fixture is now available from the root conftest
from tests.conftest import poll_db_until


@pytest.fixture(scope="module")
def setup_valuation_data(clean_db_module, api_endpoints, db_engine, poll_db_until: Callable):
    """
    A module-scoped fixture that ingests data for a simple valuation scenario,
    and waits for the calculation to complete by polling the database for the final state.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]
    portfolio_id = "E2E_VAL_PORT_01"
    security_id = "SEC_E2E_VAL"
    tx_date = "2025-07-27"

    # 1. Ingest prerequisite data
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "Medium", "investmentTimeHorizon": "Long", "portfolioType": "Advisory", "bookingCenter": "NY", "cifId": "VAL_CIF", "status": "Active"}]}
    instrument_payload = {"instruments": [{"securityId": security_id, "name": "Valuation Test Stock", "isin": "VAL12345", "instrumentCurrency": "USD", "productType": "Equity"}]}
    requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload, timeout=10)
    requests.post(f"{ingestion_url}/ingest/instruments", json=instrument_payload, timeout=10)

    # 2. Ingest transaction, market price, AND the business date to trigger the scheduler
    buy_payload = {"transactions": [{"transaction_id": "E2E_VAL_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "E2E_VAL", "security_id": security_id, "transaction_date": f"{tx_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 100.0, "gross_transaction_amount": 1000.0, "trade_currency": "USD", "currency": "USD"}]}
    price_payload = {"market_prices": [{"securityId": security_id, "priceDate": tx_date, "price": 110.0, "currency": "USD"}]}
    business_date_payload = {"business_dates": [{"businessDate": tx_date}]}

    requests.post(f"{ingestion_url}/ingest/transactions", json=buy_payload, timeout=10)
    requests.post(f"{ingestion_url}/ingest/market-prices", json=price_payload, timeout=10)
    requests.post(f"{ingestion_url}/ingest/business-dates", json=business_date_payload, timeout=10)


    # 3. Poll the database until the daily_position_snapshot is fully valued.
    # This is a reliable indicator that the entire pipeline has completed.
    query = "SELECT valuation_status FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"
    params = {"pid": portfolio_id, "sid": security_id, "date": tx_date}
    validation_func = lambda r: r is not None and r.valuation_status == 'VALUED_CURRENT'
    
    poll_db_until(
        db_engine=db_engine,
        query=query,
        validation_func=validation_func,
        params=params,
        timeout=120,
        fail_message=f"Valuation for {security_id} on {tx_date} did not complete."
    )
    
    return {"portfolio_id": portfolio_id, "query_url": query_url}


def test_full_valuation_pipeline(setup_valuation_data):
    """
    Tests the full pipeline from ingestion to position valuation, and verifies
    the final API response from the query service.
    """
    # ARRANGE
    portfolio_id = setup_valuation_data["portfolio_id"]
    query_url = setup_valuation_data["query_url"]
    
    # ACT: The pipeline has already run and been verified by the fixture; we just query the final state.
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