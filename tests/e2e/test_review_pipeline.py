# tests/e2e/test_review_pipeline.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient
from datetime import date, timedelta

# --- Test Data Constants ---
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
        {"transaction_id": "REVIEW_DEPOSIT_01", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-20T09:00:00Z", "transaction_type": "DEPOSIT", "quantity": 100000, "price": 1, "gross_transaction_amount": 100000, "trade_currency": "USD", "currency": "USD"},
        
        # Apple Purchase
        {"transaction_id": "REVIEW_BUY_AAPL", "portfolio_id": PORTFOLIO_ID, "instrument_id": "AAPL", "security_id": "SEC_AAPL", "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_CASH_SETTLE_AAPL", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "SELL", "quantity": 15000, "price": 1, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"},
        
        # Bond Purchase
        {"transaction_id": "REVIEW_BUY_BOND", "portfolio_id": PORTFOLIO_ID, "instrument_id": "UST", "security_id": "SEC_BOND", "transaction_date": "2025-08-20T11:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 980, "gross_transaction_amount": 9800, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_CASH_SETTLE_BOND", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-20T11:00:00Z", "transaction_type": "SELL", "quantity": 9800, "price": 1, "gross_transaction_amount": 9800, "trade_currency": "USD", "currency": "USD"},

        # Dividend Payment
        {"transaction_id": "REVIEW_DIV_AAPL", "portfolio_id": PORTFOLIO_ID, "instrument_id": "AAPL", "security_id": "SEC_AAPL", "transaction_date": "2025-08-25T10:00:00Z", "transaction_type": "DIVIDEND", "quantity": 0, "price": 0, "gross_transaction_amount": 120, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "REVIEW_CASH_SETTLE_DIV", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH_USD", "security_id": "CASH_USD", "transaction_date": "2025-08-25T10:00:00Z", "transaction_type": "BUY", "quantity": 120, "price": 1, "gross_transaction_amount": 120, "trade_currency": "USD", "currency": "USD"}
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
        "sections": [
            "OVERVIEW", "HOLDINGS", "TRANSACTIONS", "PERFORMANCE", "RISK_ANALYTICS"
        ]
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()

    # ASSERT
    assert response.status_code == 200
    assert data["portfolio_id"] == portfolio_id

    # --- Assert Overview Section ---
    overview = data["overview"]
    assert overview["total_market_value"] == pytest.approx(101270.00)
    assert overview["total_cash"] == pytest.approx(75320.00)
    assert overview["risk_profile"] == "Growth"
    assert overview["pnl_summary"]["total_pnl"] == pytest.approx(1150.00)

    # --- Assert Holdings Section ---
    holdings = data["holdings"]["holdingsByAssetClass"]
    assert "Equity" in holdings
    assert "Fixed Income" in holdings
    assert "Cash" in holdings
    assert holdings["Equity"][0]["security_id"] == "SEC_AAPL"
    assert holdings["Fixed Income"][0]["security_id"] == "SEC_BOND"

    # --- Assert Transactions Section ---
    transactions = data["transactions"]["transactionsByAssetClass"]
    assert "Equity" in transactions
    assert "Cash" in transactions
    txn_ids_equity = {t["transaction_id"] for t in transactions["Equity"]}
    assert "REVIEW_BUY_AAPL" in txn_ids_equity
    assert "REVIEW_DIV_AAPL" in txn_ids_equity
    assert "REVIEW_BUY_BOND" in transactions["Fixed Income"][0]["transaction_id"]
    
    # --- Assert Performance Section ---
    performance = data["performance"]
    assert performance is not None
    assert "YTD" in performance["summary"]
    assert "Since Inception" in performance["summary"]
    ytd_perf = performance["summary"]["YTD"]
    assert isinstance(ytd_perf["net_cumulative_return"], float)
    assert isinstance(ytd_perf["gross_cumulative_return"], float)
    assert ytd_perf["gross_cumulative_return"] > ytd_perf["net_cumulative_return"]
    
    # --- Assert Risk Analytics Section ---
    risk = data["riskAnalytics"]
    assert risk is not None
    assert "YTD" in risk["results"]
    ytd_risk_metrics = risk["results"]["YTD"]["metrics"]
    assert "VOLATILITY" in ytd_risk_metrics
    assert "SHARPE" in ytd_risk_metrics
    assert isinstance(ytd_risk_metrics["VOLATILITY"]["value"], float)


def test_portfolio_review_for_empty_portfolio(clean_db, e2e_api_client: E2EApiClient):
    """
    Tests that the review endpoint returns a valid, zeroed-out report for a
    portfolio that exists but has no transactions or holdings.
    """
    # ARRANGE
    empty_portfolio_id = "E2E_REVIEW_EMPTY_01"
    as_of = "2025-08-31"
    
    # 1. Ingest only the portfolio and a business date
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": empty_portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "REVIEW_EMPTY_CIF", "status": "ACTIVE", "riskExposure":"Balanced", "investmentTimeHorizon":"c", "portfolioType":"d", "bookingCenter":"e"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": as_of}]})
    
    # 2. Wait for the portfolio to be queryable
    e2e_api_client.poll_for_data(
        f"/portfolios?portfolio_id={empty_portfolio_id}",
        lambda data: data and data.get("portfolios") and len(data["portfolios"]) == 1
    )

    # 3. Define the request for the review endpoint
    api_url = f"/portfolios/{empty_portfolio_id}/review"
    request_payload = {
        "as_of_date": as_of,
        "sections": ["OVERVIEW", "HOLDINGS", "TRANSACTIONS", "PERFORMANCE", "RISK_ANALYTICS"]
    }

    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()

    # ASSERT
    assert response.status_code == 200
    assert data["portfolio_id"] == empty_portfolio_id

    # Assert Overview is zeroed out
    overview = data["overview"]
    assert overview["total_market_value"] == 0.0
    assert overview["total_cash"] == 0.0
    assert overview["risk_profile"] == "Balanced" # Static data should still appear
    assert overview["pnl_summary"]["total_pnl"] == 0.0
    
    # Assert other sections are empty/null as expected
    assert data["holdings"]["holdingsByAssetClass"] == {}
    assert data["transactions"]["transactionsByAssetClass"] == {}
    assert data["performance"] is None # No timeseries data exists
    assert data["riskAnalytics"] is None # No timeseries data exists