# tests/e2e/test_summary_pipeline.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient
from datetime import date, timedelta

# --- Test Data Constants ---
PORTFOLIO_ID = "E2E_SUM_PORT_01"
MSFT_ID = "SEC_MSFT_SUM"
IBM_ID = "SEC_IBM_SUM"
CASH_ID = "CASH_USD"
AS_OF_DATE = "2025-08-29"
PERIOD_START = "2025-08-01"

@pytest.fixture(scope="module")
def setup_summary_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the summary E2E test.
    """
    # 1. Ingest prerequisite data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "SUM_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [
        {"securityId": CASH_ID, "name": "US Dollar", "isin": "CASH_USD_ISIN", "instrumentCurrency": "USD", "productType": "Cash", "assetClass": "Cash"},
        {"securityId": MSFT_ID, "name": "Microsoft", "isin": "US_MSFT_SUM", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity", "sector": "Technology", "countryOfRisk": "US"},
        {"securityId": IBM_ID, "name": "IBM", "isin": "US_IBM_SUM", "instrumentCurrency": "USD", "productType": "Equity", "assetClass": "Equity", "sector": "Technology", "countryOfRisk": "US"}
    ]})
    all_dates = ["2025-07-31", PERIOD_START, "2025-08-05", "2025-08-10", "2025-08-15", "2025-08-20", "2025-08-22", "2025-08-26", "2025-08-27", AS_OF_DATE]
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": d} for d in all_dates]})

    # 2. Ingest a comprehensive list of transactions
    transactions = [
        {"transaction_id": "SUM_DEPOSIT_01", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH", "security_id": CASH_ID, "transaction_date": f"{PERIOD_START}T09:00:00Z", "transaction_type": "DEPOSIT", "quantity": 1000000, "price": 1, "gross_transaction_amount": 1000000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_BUY_MSFT", "portfolio_id": PORTFOLIO_ID, "instrument_id": "MSFT", "security_id": MSFT_ID, "transaction_date": "2025-08-05T10:00:00Z", "transaction_type": "BUY", "quantity": 1000, "price": 300, "gross_transaction_amount": 300000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_CASH_SETTLE_1", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH", "security_id": CASH_ID, "transaction_date": "2025-08-05T10:00:00Z", "transaction_type": "SELL", "quantity": 300000, "price": 1, "gross_transaction_amount": 300000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_TRANSFER_IN_IBM", "portfolio_id": PORTFOLIO_ID, "instrument_id": "IBM", "security_id": IBM_ID, "transaction_date": "2025-08-10T10:00:00Z", "transaction_type": "TRANSFER_IN", "quantity": 100, "price": 150, "gross_transaction_amount": 15000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_SELL_MSFT", "portfolio_id": PORTFOLIO_ID, "instrument_id": "MSFT", "security_id": MSFT_ID, "transaction_date": "2025-08-15T10:00:00Z", "transaction_type": "SELL", "quantity": 200, "price": 320, "gross_transaction_amount": 64000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_CASH_SETTLE_2", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH", "security_id": CASH_ID, "transaction_date": "2025-08-15T10:00:00Z", "transaction_type": "BUY", "quantity": 64000, "price": 1, "gross_transaction_amount": 64000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_FEE_01", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH", "security_id": CASH_ID, "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "FEE", "quantity": 1, "price": 50, "gross_transaction_amount": 50, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_DIVIDEND_MSFT", "portfolio_id": PORTFOLIO_ID, "instrument_id": "MSFT", "security_id": MSFT_ID, "transaction_date": "2025-08-22T10:00:00Z", "transaction_type": "DIVIDEND", "quantity": 0, "price": 0, "gross_transaction_amount": 400, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_CASH_SETTLE_3", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH", "security_id": CASH_ID, "transaction_date": "2025-08-22T10:00:00Z", "transaction_type": "BUY", "quantity": 400, "price": 1, "gross_transaction_amount": 400, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_WITHDRAWAL_01", "portfolio_id": PORTFOLIO_ID, "instrument_id": "CASH", "security_id": CASH_ID, "transaction_date": "2025-08-26T10:00:00Z", "transaction_type": "WITHDRAWAL", "quantity": 10000, "price": 1, "gross_transaction_amount": 10000, "trade_currency": "USD", "currency": "USD"},
        {"transaction_id": "SUM_TRANSFER_OUT_MSFT", "portfolio_id": PORTFOLIO_ID, "instrument_id": "MSFT", "security_id": MSFT_ID, "transaction_date": "2025-08-27T10:00:00Z", "transaction_type": "TRANSFER_OUT", "quantity": 50, "price": 330, "gross_transaction_amount": 16500, "trade_currency": "USD", "currency": "USD"}
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Ingest market prices
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"securityId": MSFT_ID, "priceDate": AS_OF_DATE, "price": 340.0, "currency": "USD"},
        {"securityId": IBM_ID, "priceDate": AS_OF_DATE, "price": 155.0, "currency": "USD"},
        {"securityId": CASH_ID, "priceDate": AS_OF_DATE, "price": 1.0, "currency": "USD"}
    ]})
    
    # 4. Poll until the final snapshot is valued
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
    portfolio_id = setup_summary_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/summary"
    request_payload = {
        "as_of_date": AS_OF_DATE,
        "period": {"type": "EXPLICIT", "from": PERIOD_START, "to": AS_OF_DATE},
        "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY", "ALLOCATION"],
        "allocation_dimensions": ["ASSET_CLASS", "SECTOR", "COUNTRY_OF_RISK"]
    }

    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()
    assert response.status_code == 200

    # Expected Final State Calculations:
    # Cash: 1M(dep) - 300k(buy) + 64k(sell) - 50(fee) + 400(div) - 10k(w/d) = 754,350
    # MSFT shares: 1000(buy) - 200(sell) - 50(xfer) = 750
    # IBM shares: 100(xfer)
    # Wealth:
    # Cash MV = 754,350
    # MSFT MV = 750 * 340 = 255,000
    # IBM MV = 100 * 155 = 15,500
    # Total MV = 754350 + 255000 + 15500 = 1,024,850
    assert data["wealth"]["total_market_value"] == pytest.approx(1024850.00)
    assert data["wealth"]["total_cash"] == pytest.approx(754350.00)

    # Activity & Income
    activity = data["activitySummary"]
    assert activity["total_deposits"] == pytest.approx(1000000.00)
    assert activity["total_withdrawals"] == pytest.approx(-10000.00)
    assert activity["total_transfers_in"] == pytest.approx(15000.00)
    assert activity["total_transfers_out"] == pytest.approx(-16500.00)
    assert activity["total_fees"] == pytest.approx(-50.00)
    assert data["incomeSummary"]["total_dividends"] == pytest.approx(400.00)
    
    # P&L
    # Realized P&L = 200 * (320 - 300) = 4000
    # U-PNL start = 0
    # U-PNL end: MSFT=750*(340-300)=30000. IBM=100*(155-150)=500. Total=30500
    pnl = data["pnlSummary"]
    assert pnl["net_new_money"] == pytest.approx(988500.00)
    assert pnl["realized_pnl"] == pytest.approx(4000.00)
    assert pnl["unrealized_pnl_change"] == pytest.approx(30500.00)
    assert pnl["total_pnl"] == pytest.approx(34500.00)