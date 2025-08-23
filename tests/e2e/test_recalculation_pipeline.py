# tests/e2e/test_recalculation_pipeline.py
import pytest
import requests
import time
from decimal import Decimal

# --- Constants ---
PORTFOLIO_ID = "E2E_RECALC_01"
SECURITY_ID = "SEC_RECALC_AAPL"
DAY_1 = "2025-08-04"
DAY_2 = "2025-08-05"
DAY_3 = "2025-08-06"

@pytest.fixture(scope="module")
def setup_recalculation_scenario(clean_db_module, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that ingests an initial set of transactions
    and waits for the pipeline to settle into a correct state, ready for
    the recalculation trigger.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]

    # 1. Ingest prerequisite data
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "RECALC_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": SECURITY_ID, "name": "Recalc Apple", "isin": "RECALC_AAPL_ISIN", "instrumentCurrency": "USD", "productType": "Equity"}]})
    requests.post(f"{ingestion_url}/ingest/business-dates", json={"business_dates": [{"businessDate": DAY_1}, {"businessDate": DAY_2}, {"businessDate": DAY_3}]})

    # 2. Ingest initial transaction sequence
    transactions = [
        # Day 2: Buy 100 @ $100
        {"transaction_id": "RECALC_BUY_01", "portfolio_id": PORTFOLIO_ID, "security_id": SECURITY_ID, "transaction_date": f"{DAY_2}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 100, "gross_transaction_amount": 10000, "trade_currency": "USD", "currency": "USD"},
        # Day 3: Sell 40 @ $120
        {"transaction_id": "RECALC_SELL_01", "portfolio_id": PORTFOLIO_ID, "security_id": SECURITY_ID, "transaction_date": f"{DAY_3}T10:00:00Z", "transaction_type": "SELL", "quantity": 40, "price": 120, "gross_transaction_amount": 4800, "trade_currency": "USD", "currency": "USD"}
    ]
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": transactions})
    
    # 3. Poll until the initial state is correct.
    # Initial P&L = (40 * 120) - (40 * 100) = 4800 - 4000 = $800
    poll_url = f"{query_url}/portfolios/{PORTFOLIO_ID}/transactions"
    
    def validation_func(data):
        if not (data.get("transactions") and len(data["transactions"]) == 2):
            return False
        sell_tx = next((t for t in data["transactions"] if t["transaction_type"] == "SELL"), None)
        return sell_tx and sell_tx.get("realized_gain_loss") == "800.0000000000"

    poll_for_data(poll_url, validation_func, timeout=90)
    
    return {"ingestion_url": ingestion_url, "query_url": query_url}


def test_backdated_transaction_triggers_recalculation(setup_recalculation_scenario, api_endpoints, poll_for_data):
    """
    Tests the full recalculation pipeline:
    1. Ingest a back-dated transaction.
    2. Verify it triggers a recalculation job.
    3. Poll the query API until the realized P&L of a later transaction is
       updated, proving the entire pipeline ran successfully.
    """
    # ARRANGE: URLs from fixtures
    ingestion_url = setup_recalculation_scenario["ingestion_url"]
    query_url = setup_recalculation_scenario["query_url"]
    
    # ACT: Ingest a back-dated transaction on DAY 1.
    # This BUY of 100 @ $90 should become the first lot, changing the cost basis for the Day 3 SELL.
    backdated_buy = {
        "transactions": [
            {"transaction_id": "RECALC_BUY_BACKDATED", "portfolio_id": PORTFOLIO_ID, "security_id": SECURITY_ID, "transaction_date": f"{DAY_1}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 90, "gross_transaction_amount": 9000, "trade_currency": "USD", "currency": "USD"}
        ]
    }
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=backdated_buy)
    assert response.status_code == 202

    # ASSERT: Poll for the *new* correct state.
    # New Cost Basis: First lot is 100 @ $90. The sell of 40 shares will match against this.
    # New P&L = (40 * 120) - (40 * 90) = 4800 - 3600 = $1200
    poll_url = f"{query_url}/portfolios/{PORTFOLIO_ID}/transactions"

    def new_validation_func(data):
        if not (data.get("transactions") and len(data["transactions"]) == 3):
            return False
        sell_tx = next((t for t in data["transactions"] if t["transaction_id"] == "RECALC_SELL_01"), None)
        return sell_tx and sell_tx.get("realized_gain_loss") == "1200.0000000000"

    # Use a longer timeout as the recalculation involves cleanup and a full replay.
    poll_for_data(poll_url, new_validation_func, timeout=120, fail_message="Recalculation did not result in the correct P&L.")