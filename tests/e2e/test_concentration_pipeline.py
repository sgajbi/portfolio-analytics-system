# tests/e2e/test_concentration_pipeline.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient
from datetime import date

# --- Test Data Constants ---
PORTFOLIO_ID = "E2E_CONC_01"
AS_OF_DATE = "2025-08-31"
SEC_A_ID = "SEC_CONC_A"
SEC_B_ID = "SEC_CONC_B"
SEC_C_ID = "SEC_CONC_C"

@pytest.fixture(scope="module")
def setup_concentration_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the full
    concentration E2E test and waits for the pipeline to complete.
    """
    # 1. Ingest prerequisite data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "CONC_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"securityId": SEC_A_ID, "name": "CONC_A", "isin": "ISIN_CONC_A", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity"},
        {"securityId": SEC_B_ID, "name": "CONC_B", "isin": "ISIN_CONC_B", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity"},
        {"securityId": SEC_C_ID, "name": "CONC_C", "isin": "ISIN_CONC_C", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity"}
    ]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": AS_OF_DATE}]})

    # 2. Ingest transactions to create positions
    transactions = [
        {"transaction_id": "CONC_BUY_A", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CONC_A_TICKER", "security_id": SEC_A_ID, "transaction_date": f"{AS_OF_DATE}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "CONC_BUY_B", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CONC_B_TICKER", "security_id": SEC_B_ID, "transaction_date": f"{AS_OF_DATE}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "CONC_BUY_C", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CONC_C_TICKER", "security_id": SEC_C_ID, "transaction_date": f"{AS_OF_DATE}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 1, "gross_transaction_amount": 100, "trade_currency": "USD", "currency": "USD"}
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Ingest market prices that will result in the desired weights (60%, 25%, 15%)
    prices = [
        {"securityId": SEC_A_ID, "priceDate": AS_OF_DATE, "price": 600.0, "currency": "USD"}, # 100 * 600 = 60,000
        {"securityId": SEC_B_ID, "priceDate": AS_OF_DATE, "price": 250.0, "currency": "USD"}, # 100 * 250 = 25,000
        {"securityId": SEC_C_ID, "priceDate": AS_OF_DATE, "price": 150.0, "currency": "USD"}  # 100 * 150 = 15,000
    ] # Total Market Value = 100,000
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": prices})
    
    # 4. Poll until the final snapshot is valued for all positions
    poll_db_until(
        query="SELECT count(*) FROM daily_position_snapshots WHERE portfolio_id = :pid AND date = :date AND valuation_status = 'VALUED_CURRENT'",
        params={"pid": PORTFOLIO_ID, "date": AS_OF_DATE},
        validation_func=lambda r: r is not None and r[0] == 3,
        timeout=120,
        fail_message=f"Pipeline did not value all 3 positions for {AS_OF_DATE}."
    )
    return {"portfolio_id": PORTFOLIO_ID}

def test_bulk_concentration_e2e(setup_concentration_data, e2e_api_client: E2EApiClient):
    """
    Tests the full pipeline by calling the concentration endpoint and verifying the
    bulk concentration calculations.
    """
    portfolio_id = setup_concentration_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/concentration"
    request_payload = {
        "scope": {"as_of_date": AS_OF_DATE},
        "metrics": ["BULK"],
        "options": {"bulk_top_n": [2]}
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()

    # ASSERT
    assert response.status_code == 200
    
    # Assert Summary
    assert data["summary"]["portfolio_market_value"] == pytest.approx(100000.0)

    # Assert Bulk Concentration
    bulk_data = data["bulk_concentration"]
    assert bulk_data["single_position_weight"] == pytest.approx(0.60)
    assert bulk_data["top_n_weights"]["2"] == pytest.approx(0.85) # 60% + 25%
    assert bulk_data["hhi"] == pytest.approx(0.445) # 0.6^2 + 0.25^2 + 0.15^2