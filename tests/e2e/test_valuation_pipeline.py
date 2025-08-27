# tests/e2e/test_valuation_pipeline.py
import pytest
from decimal import Decimal
from typing import Callable
from .api_client import E2EApiClient


@pytest.fixture(scope="module")
def setup_valuation_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until: Callable):
    """
    A module-scoped fixture that ingests data for a simple valuation scenario,
    and waits for the calculation to complete by polling the database for the final state.
    """
    portfolio_id = "E2E_VAL_PORT_01"
    security_id = "SEC_E2E_VAL"
    tx_date = "2025-07-27"

    # 1. Ingest prerequisite data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "riskExposure": "Medium", "investmentTimeHorizon": "Long", "portfolioType": "Advisory", "bookingCenter": "NY", "cifId": "VAL_CIF", "status": "ACTIVE"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"securityId": security_id, "name": "Valuation Test Stock", "isin": "VAL12345", "instrumentCurrency": "USD", "productType": "Equity"}]})

    # 2. Ingest transaction, market price, AND the business date to trigger the scheduler
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [{"transaction_id": "E2E_VAL_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "E2E_VAL", "security_id": security_id, "transaction_date": f"{tx_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 100.0, "gross_transaction_amount": 1000.0, "trade_currency": "USD", "currency": "USD"}]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [{"securityId": security_id, "priceDate": tx_date, "price": 110.0, "currency": "USD"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": tx_date}]})


    # 3. Poll the database until the daily_position_snapshot is fully valued.
    # This is a reliable indicator that the entire pipeline has completed.
    query = "SELECT valuation_status FROM daily_position_snapshots WHERE portfolio_id = :pid AND security_id = :sid AND date = :date"
    params = {"pid": portfolio_id, "sid": security_id, "date": tx_date}
    validation_func = lambda r: r is not None and r.valuation_status == 'VALUED_CURRENT'
    
    poll_db_until(
        query=query,
        validation_func=validation_func,
        params=params,
        timeout=120,
        fail_message=f"Valuation for {security_id} on {tx_date} did not complete."
    )
    
    return {"portfolio_id": portfolio_id}


def test_full_valuation_pipeline(setup_valuation_data, e2e_api_client: E2EApiClient):
    """
    Tests the full pipeline from ingestion to position valuation, and verifies
    the final API response from the query service.
    """
    # ARRANGE
    portfolio_id = setup_valuation_data["portfolio_id"]
    
    # ACT: The pipeline has already run and been verified by the fixture; we just query the final state.
    api_response = e2e_api_client.query(f"/portfolios/{portfolio_id}/positions")
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