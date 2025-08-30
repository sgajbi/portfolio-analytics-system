# tests/e2e/test_summary_pipeline.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient

# --- Test Data Constants ---
PORTFOLIO_ID = "E2E_SUM_PORT_01"
MSFT_ID = "SEC_MSFT_SUM"
ROG_ID = "SEC_ROG_SUM" # Roche, in CHF
CASH_ID = "CASH_USD"
AS_OF_DATE = "2025-08-29"
PERIOD_START = "2025-08-01"

@pytest.fixture(scope="module")
def setup_summary_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the summary E2E test.
    """
    # 1. Ingest prerequisite data (Portfolio, Instruments with new fields)
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "SUM_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"securityId": CASH_ID, "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash", "assetClass": "Cash"},
        {"securityId": MSFT_ID, "name": "Microsoft", "isin": "US_MSFT_SUM", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity", "sector": "Technology", "countryOfRisk": "US"},
        {"securityId": ROG_ID, "name": "Roche Holding", "isin": "CH_ROG_SUM", "instrumentCurrency": "CHF", "productType": "Equity", "assetClass": "Equity", "sector": "Healthcare", "countryOfRisk": "CH"}
    ]})
    e2e_api_client.ingest("/ingest/fx-rates", {"fx_rates": [
        {"fromCurrency": "CHF", "toCurrency": "USD", "rateDate": "2025-08-05", "rate": "1.10"},
        {"fromCurrency": "CHF", "toCurrency": "USD", "rateDate": AS_OF_DATE, "rate": "1.12"}
    ]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": d} for d in [PERIOD_START, "2025-08-05", "2025-08-15", "2025-08-20", AS_OF_DATE]]})

    # 2. Ingest transactions over the period
    transactions = [
        {"transaction_id": "SUM_DEPOSIT_01", "portfolio_id": PORTFOLIO_ID, "security_id": CASH_ID, "transaction_date": f"{PERIOD_START}T09:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1, "gross_transaction_amount": 1000000},
        {"transaction_id": "SUM_BUY_MSFT", "portfolio_id": PORTFOLIO_ID, "security_id": MSFT_ID, "transaction_date": "2025-08-05T10:00:00Z", "transaction_type": "BUY", "quantity": 1000, "price": 300, "gross_transaction_amount": 300000},
        {"transaction_id": "SUM_BUY_ROG", "portfolio_id": PORTFOLIO_ID, "security_id": ROG_ID, "transaction_date": "2025-08-05T11:00:00Z", "transaction_type": "BUY", "quantity": 2000, "price": 250, "gross_transaction_amount": 500000, "trade_currency": "CHF", "currency": "CHF"},
        {"transaction_id": "SUM_SELL_MSFT", "portfolio_id": PORTFOLIO_ID, "security_id": MSFT_ID, "transaction_date": "2025-08-15T10:00:00Z", "transaction_type": "SELL", "quantity": 200, "price": 320, "gross_transaction_amount": 64000},
        {"transaction_id": "SUM_FEE_01", "portfolio_id": PORTFOLIO_ID, "security_id": CASH_ID, "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "FEE", "quantity": 1, "price": 50, "gross_transaction_amount": 50}
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Ingest market prices for the as_of_date
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"securityId": MSFT_ID, "priceDate": AS_OF_DATE, "price": 330.0, "currency": "USD"},
        {"securityId": ROG_ID, "priceDate": AS_OF_DATE, "price": 260.0, "currency": "CHF"},
        {"securityId": CASH_ID, "priceDate": AS_OF_DATE, "price": 1.0, "currency": "USD"}
    ]})
    
    # 4. Poll until the final snapshot is valued, ensuring the pipeline has completed
    poll_db_until(
        query="SELECT count(*) FROM daily_position_snapshots WHERE portfolio_id = :pid AND date = :date AND valuation_status = 'VALUED_CURRENT'",
        params={"pid": PORTFOLIO_ID, "date": AS_OF_DATE},
        validation_func=lambda r: r is not None and r[0] >= 3,
        timeout=180,
        fail_message=f"Pipeline did not value all 3 positions for {AS_OF_DATE}."
    )
    return {"portfolio_id": PORTFOLIO_ID}

def test_portfolio_summary_endpoint(setup_summary_data, e2e_api_client: E2EApiClient):
    """
    Tests the full summary pipeline by calling the endpoint and verifying all calculations.
    """
    # ARRANGE
    portfolio_id = setup_summary_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/summary"
    request_payload = {
        "as_of_date": AS_OF_DATE,
        "period": {"type": "EXPLICIT", "from": PERIOD_START, "to": AS_OF_DATE},
        "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY", "ALLOCATION"],
        "allocation_dimensions": ["ASSET_CLASS", "SECTOR", "COUNTRY_OF_RISK"]
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()

    # ASSERT
    assert response.status_code == 200

    # Wealth
    # Cash = 1M - 300k - (500k CHF * 1.1) + 64k - 50 = 213950
    # MSFT = 800 * 330 = 264000
    # ROG = 2000 * 260 CHF * 1.12 = 582400
    # Total = 213950 + 264000 + 582400 = 1060350
    assert Decimal(data["wealth"]["total_market_value"]).quantize(Decimal("0.01")) == Decimal("1060350.00")
    assert Decimal(data["wealth"]["total_cash"]).quantize(Decimal("0.01")) == Decimal("213950.00")

    # Activity & Income
    assert Decimal(data["activitySummary"]["total_inflows"]).quantize(Decimal("0.01")) == Decimal("1000000.00")
    assert Decimal(data["activitySummary"]["total_outflows"]).quantize(Decimal("0.01")) == Decimal("0.00")
    assert Decimal(data["activitySummary"]["total_fees"]).quantize(Decimal("0.01")) == Decimal("-50.00")
    assert Decimal(data["incomeSummary"]["total_dividends"]).quantize(Decimal("0.01")) == Decimal("0.00")

    # P&L
    # Realized P&L = 200 * (320 - 300) = 4000
    # U-PNL start = 0
    # U-PNL end: MSFT = 800 * (330 - 300) = 24000. ROG = 2000 * (260*1.12 - 250*1.10) = 2000 * (291.2 - 275) = 32400. Total = 56400
    pnl = data["pnlSummary"]
    assert Decimal(pnl["net_new_money"]).quantize(Decimal("0.01")) == Decimal("1000000.00")
    assert Decimal(pnl["realized_pnl"]).quantize(Decimal("0.01")) == Decimal("4000.00")
    assert Decimal(pnl["unrealized_pnl_change"]).quantize(Decimal("0.01")) == Decimal("56400.00")
    assert Decimal(pnl["total_pnl"]).quantize(Decimal("0.01")) == Decimal("60400.00")

    # Allocation
    alloc = data["allocation"]
    assert alloc["byAssetClass"][0]["group"] == "Cash"
    assert Decimal(alloc["byAssetClass"][0]["market_value"]).quantize(Decimal("0.01")) == Decimal("213950.00")
    assert alloc["byAssetClass"][1]["group"] == "Equity"
    assert Decimal(alloc["byAssetClass"][1]["market_value"]).quantize(Decimal("0.01")) == Decimal("846400.00") # MSFT + ROG
    
    assert alloc["bySector"][0]["group"] == "Healthcare"
    assert alloc["bySector"][1]["group"] == "Technology"
    assert alloc["bySector"][2]["group"] == "Unclassified" # Cash
    assert Decimal(alloc["bySector"][2]["market_value"]).quantize(Decimal("0.01")) == Decimal("213950.00")