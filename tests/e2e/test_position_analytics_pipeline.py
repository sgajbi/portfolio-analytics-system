# tests/e2e/test_position_analytics_pipeline.py
import pytest
from decimal import Decimal
from datetime import date, timedelta
from .api_client import E2EApiClient

# --- Test Data Constants ---
PORTFOLIO_ID = "E2E_POS_ANALYTICS_01"
SECURITY_ID = "SEC_BAYN_DE" # Bayer AG (EUR stock)
AS_OF_DATE = "2025-08-25"

@pytest.fixture(scope="module")
def setup_position_analytics_data(clean_db_module, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture that ingests all necessary data for the full
    position-level analytics E2E test.
    """
    # 1. Ingest prerequisite data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": PORTFOLIO_ID, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "POS_ANALYTICS_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"securityId": SECURITY_ID, "name": "Bayer AG", "isin": "DE000BAY0017", "instrumentCurrency": "EUR", "productType": "Equity", "assetClass": "Equity"}]})
    
    dates = ["2025-08-20", "2025-08-21", AS_OF_DATE]
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": d} for d in dates]})
    e2e_api_client.ingest("/ingest/fx-rates", {"fx_rates": [
        {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-08-20", "rate": "1.10"},
        {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": "2025-08-21", "rate": "1.15"},
        {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": AS_OF_DATE, "rate": "1.20"}
    ]})

    # 2. Ingest transactions to build a history
    transactions = [
        {"transaction_id": "PA_BUY_01", "portfolio_id": PORTFOLIO_ID, "instrument_id": "BAYN", "security_id": SECURITY_ID, "transaction_date": "2025-08-20T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 50, "gross_transaction_amount": 5000, "trade_currency": "EUR", "currency": "EUR"},
        {"transaction_id": "PA_DIV_01", "portfolio_id": PORTFOLIO_ID, "instrument_id": "BAYN", "security_id": SECURITY_ID, "transaction_date": "2025-08-21T10:00:00Z", "transaction_type": "DIVIDEND", "quantity": 0, "price": 0, "gross_transaction_amount": 75, "trade_currency": "EUR", "currency": "EUR"},
    ]
    e2e_api_client.ingest("/ingest/transactions", {"transactions": transactions})
    
    # 3. Ingest market prices for valuation
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [
        {"securityId": SECURITY_ID, "priceDate": "2025-08-20", "price": 52.0, "currency": "EUR"},
        {"securityId": SECURITY_ID, "priceDate": "2025-08-21", "price": 53.0, "currency": "EUR"},
        {"securityId": SECURITY_ID, "priceDate": AS_OF_DATE, "price": 55.0, "currency": "EUR"}
    ]})
    
    # 4. Poll until the timeseries for ALL relevant days are generated.
    poll_db_until(
        query="SELECT count(*) FROM position_timeseries WHERE portfolio_id = :pid AND security_id = :sid AND date IN :dates",
        params={"pid": PORTFOLIO_ID, "sid": SECURITY_ID, "dates": tuple(dates)},
        validation_func=lambda r: r is not None and r[0] == len(dates),
        timeout=180,
        fail_message=f"Pipeline did not generate all {len(dates)} position_timeseries records."
    )
    return {"portfolio_id": PORTFOLIO_ID}

def test_position_analytics_pipeline(setup_position_analytics_data, e2e_api_client: E2EApiClient):
    """
    Tests the full position analytics pipeline by calling the endpoint and
    verifying all calculated fields in a dual-currency context.
    """
    portfolio_id = setup_position_analytics_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/positions-analytics"
    request_payload = {
        "asOfDate": AS_OF_DATE,
        "sections": ["BASE", "INSTRUMENT_DETAILS", "VALUATION", "INCOME", "PERFORMANCE"],
        "performanceOptions": {
            "periods": ["SI"]
        }
    }

    # ACT
    # The short sleep is removed as the polling is now sufficient.
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()

    # ASSERT
    assert response.status_code == 200
    assert len(data["positions"]) > 0
    position = next(p for p in data["positions"] if p["securityId"] == SECURITY_ID)

    # Assert Base section
    assert position["heldSinceDate"] == "2025-08-20"
    
    # Assert Income section
    assert position["income"]["local"]["amount"] == pytest.approx(75.0)
    assert position["income"]["local"]["currency"] == "EUR"
    # Income (Base) = 75 EUR * 1.15 (FX on dividend date) = 86.25 USD
    assert position["income"]["base"]["amount"] == pytest.approx(86.25)
    assert position["income"]["base"]["currency"] == "USD"
    
    # Assert Valuation section
    assert position["valuation"]["costBasis"]["local"]["amount"] == pytest.approx(5000.0)
    assert position["valuation"]["costBasis"]["base"]["amount"] == pytest.approx(5500.0)
    assert position["valuation"]["marketValue"]["local"]["amount"] == pytest.approx(5500.0)
    assert position["valuation"]["marketValue"]["base"]["amount"] == pytest.approx(6600.0)
    
    # Assert Performance section
    # The Time-Weighted Return (TWR) is calculated by linking daily returns.
    # The correct TWR for this period is ~8.49%.
    performance = position["performance"]["SI"]
    assert performance["localReturn"] == pytest.approx(8.49, abs=1e-2)