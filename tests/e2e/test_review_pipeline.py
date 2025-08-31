# tests/e2e/test_review_pipeline.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient

PORTFOLIO_ID = "E2E_REVIEW_01"
AS_OF_DATE = "2025-08-30"

@pytest.fixture(scope="module")
def setup_review_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the full
    portfolio review E2E test.
    """
    # 1. Ingest prerequisite data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "REVIEW_CIF", "status": "ACTIVE", "riskExposure":"Growth", "investmentTimeHorizon":"b", "portfolioType":"Discretionary", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"securityId": "CASH_USD", "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash", "assetClass": "Cash"},
        {"securityId": "SEC_AAPL", "name": "Apple Inc.", "isin": "US_AAPL_REVIEW", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity"},
        {"securityId": "SEC_BOND", "name": "US Treasury Bond", "isin": "US_BOND_REVIEW", "instrumentCurrency": "USD", "productType": "Bond", "assetClass": "Fixed Income"}
    ]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": "2025-08-20"}, {"businessDate": "2025-08-25"}, {"businessDate": AS_OF_DATE}]})

    # 2. Ingest transactions to build a history
    transactions = [
        {"transaction_id": "REVIEW_DEPOSIT_01", "portfolio_id": PORTFOLIO_ID, "security_id": "CASH_USD", "transaction_date": "2025-08-20T09:00:00Z", "transaction_type": "DEPOSIT", "quantity": 100000, "price": 1, "gross_transaction_amount": 100000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_BUY_AAPL", "portfolio_id": PORTFOLIO_ID, "security_id": "SEC_AAPL", "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_BUY_BOND", "portfolio_id": PORTFOLIO_ID, "security_id": "SEC_BOND", "transaction_date": "2025-08-20T11:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 980, "gross_transaction_amount": 9800, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_DIV_AAPL", "portfolio_id": PORTFOLIO_ID, "security_id": "SEC_AAPL", "transaction_date": "2025-08-25T10:00:00Z", "transaction_type": "DIVIDEND", "quantity": 0, "price": 0, "gross_transaction_amount": 120, "trade_currency": "USD", "currency": "USD"}
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Ingest market prices for valuation
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"securityId": "SEC_AAPL", "priceDate": AS_OF_DATE, "price": 160.0, "currency": "USD"},
        {"securityId": "SEC_BOND", "priceDate": AS_OF_DATE, "price": 995.0, "currency": "USD"},
        {"securityId": "CASH_USD", "priceDate": AS_OF_DATE, "price": 1.0, "currency": "USD"}
    ]})
    
    # 4. Poll until the final day's timeseries is generated
    poll_db_until(
        query="SELECT 1 FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": PORTFOLIO_ID, "date": AS_OF_DATE},
        validation_func=lambda r: r is not None,
        timeout=180,
        fail_message=f"Pipeline did not generate portfolio_timeseries for {AS_OF_DATE}."
    )
    return {"portfolio_id": PORTFOLIO_ID}


def test_portfolio_review_endpoint(setup_review_data, e2e_api_client: E2EApiClient):
    """
    Tests the full review pipeline by calling the endpoint and verifying key
    sections of the aggregated report.
    """
    portfolio_id = setup_review_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/review"
    request_payload = {
        "as_of_date": AS_OF_DATE,
        "sections": ["OVERVIEW", "HOLDINGS", "TRANSACTIONS"]
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()

    # ASSERT
    assert response.status_code == 200
    assert data["portfolio_id"] == portfolio_id

    # --- Assert Overview Section ---
    # Expected MV = (100 * 160) + (10 * 995) + (100000 - 15000 - 9800 + 120) = 16000 + 9950 + 75320 = 101270
    # Expected U-PNL = (16000 - 15000) + (9950 - 9800) = 1000 + 150 = 1150
    overview = data["overview"]
    assert Decimal(overview["total_market_value"]).quantize(Decimal("0.01")) == Decimal("101270.00")
    assert Decimal(overview["total_cash"]).quantize(Decimal("0.01")) == Decimal("75320.00")
    assert overview["risk_profile"] == "Growth"
    assert Decimal(overview["pnl_summary"]["total_pnl"]).quantize(Decimal("0.01")) == Decimal("1150.00")

    # --- Assert Holdings Section ---
    holdings = data["holdings"]["holdingsByAssetClass"]
    assert "Equity" in holdings
    assert "Fixed Income" in holdings
    assert "Cash" in holdings
    assert holdings["Equity"][0]["security_id"] == "SEC_AAPL"
    assert holdings["Fixed Income"][0]["security_id"] == "SEC_BOND"

    # --- Assert Transactions Section ---
    transactions = data["transactions"]["transactionsByAssetClass"]
    assert "Equity/Other" in transactions
    assert "Cash" in transactions
    txn_ids = {t["transaction_id"] for t in transactions["Equity/Other"]}
    assert "REVIEW_BUY_AAPL" in txn_ids
    assert "REVIEW_BUY_BOND" in txn_ids
    assert "REVIEW_DIV_AAPL" in txn_ids