# tests/e2e/test_reprocessing_workflow.py
import pytest
from decimal import Decimal
from datetime import date
from .api_client import E2EApiClient

@pytest.fixture(scope="module")
def setup_reprocessing_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that sets up an initial state for a position,
    in preparation for a back-dated transaction.
    """
    portfolio_id = "E2E_REPRO_01"
    security_id = "SEC_REPRO_AAPL"
    day1, day2 = "2025-09-01", "2025-09-02"

    # 1. Ingest prerequisites
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "REPRO_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"securityId": security_id, "name": "Apple Repro", "isin": "US0378331005_REPRO", "instrumentCurrency": "USD", "productType": "Equity"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": day1}, {"businessDate": day2}]})

    # 2. Ingest initial transaction on Day 2
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [{"transaction_id": "REPRO_BUY_DAY2", "portfolio_id": portfolio_id, "instrument_id": "AAPL", "security_id": security_id, "transaction_date": f"{day2}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 200, "gross_transaction_amount": 20000, "trade_currency": "USD", "currency": "USD"}]})
    
    # 3. Poll until the position state is created and has the initial epoch (0)
    poll_db_until(
        query="SELECT epoch FROM position_state WHERE portfolio_id = :pid AND security_id = :sid",
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: r is not None and r.epoch == 0,
        timeout=60,
        fail_message="Initial position_state (epoch 0) was not created."
    )
    
    return {"portfolio_id": portfolio_id, "security_id": security_id}

def test_back_dated_transaction_triggers_reprocessing_and_corrects_state(
    setup_reprocessing_data, e2e_api_client: E2EApiClient, poll_db_until
):
    """
    Verifies that ingesting a back-dated transaction triggers an epoch increment
    and leads to a corrected final position state.
    """
    # ARRANGE
    portfolio_id = setup_reprocessing_data["portfolio_id"]
    security_id = setup_reprocessing_data["security_id"]
    day1 = "2025-09-01"

    # Initial state (from fixture): 100 shares bought on Day 2.
    # We now ingest a sale of 20 shares on Day 1 (back-dated).
    back_dated_payload = {"transactions": [{"transaction_id": "REPRO_SELL_DAY1", "portfolio_id": portfolio_id, "instrument_id": "AAPL", "security_id": security_id, "transaction_date": f"{day1}T11:00:00Z", "transaction_type": "SELL", "quantity": 20, "price": 190, "gross_transaction_amount": 3800, "trade_currency": "USD", "currency": "USD"}]}

    # ACT: Ingest the back-dated transaction
    e2e_api_client.ingest("/ingest/transactions", back_dated_payload)

    # ASSERT 1: The epoch must increment to 1.
    # We poll until the system has completed the reprocessing cycle.
    poll_db_until(
        query="SELECT epoch, status FROM position_state WHERE portfolio_id = :pid AND security_id = :sid",
        params={"pid": portfolio_id, "sid": security_id},
        validation_func=lambda r: r is not None and r.epoch == 1 and r.status == 'CURRENT',
        timeout=90,
        fail_message="Reprocessing did not complete and increment epoch to 1."
    )

    # ASSERT 2: The final position must be correct.
    # After reprocessing, the history is: SELL 20 (invalid), BUY 100.
    # The final quantity should be 100, but the position history will show the invalid sell.
    # The cost basis should be based on the BUY only.
    response = e2e_api_client.query(f"/portfolios/{portfolio_id}/positions")
    data = response.json()
    
    assert len(data["positions"]) == 1
    position = data["positions"][0]
    
    # The final quantity should be 100. The cost basis is from the single BUY.
    assert Decimal(position["quantity"]).quantize(Decimal("0.01")) == Decimal("100.00")
    assert Decimal(position["cost_basis"]).quantize(Decimal("0.01")) == Decimal("20000.00")