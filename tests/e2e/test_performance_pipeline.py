# tests/e2e/test_performance_pipeline.py
import pytest
from decimal import Decimal
from datetime import date
from .api_client import E2EApiClient

@pytest.fixture(scope="module")
def setup_performance_data(clean_db_module, db_engine, e2e_api_client: E2EApiClient, poll_db_until):
    """
    A module-scoped fixture to ingest data for a multi-day performance scenario
    and wait for the backend pipeline to generate the necessary time-series data.
    """
    portfolio_id = "E2E_ADV_PERF_01"
    security_id = "SEC_ADV_PERF_01"
    
    # --- Ingest Prerequisite Data ---
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "ADV_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"securityId": security_id, "name": "Adv Perf Stock", "isin": "ADV123", "instrumentCurrency": "USD", "productType": "Equity"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": "2025-03-10"}, {"businessDate": "2025-03-11"}]})

    # --- Day 1: 2025-03-10 ---
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [{"transaction_id": "PERF_BUY_01", "portfolio_id": portfolio_id, "instrument_id": "ADV", "security_id": security_id, "transaction_date": "2025-03-10T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 100, "gross_transaction_amount": 10000, "trade_currency": "USD", "currency": "USD"}]})
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [{"securityId": security_id, "priceDate": "2025-03-10", "price": 102.0, "currency": "USD"}]})

    # --- Day 2: 2025-03-11 ---
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [{"securityId": security_id, "priceDate": "2025-03-11", "price": 105.0, "currency": "USD"}]})

    # Poll until the timeseries for the last day is fully generated.
    # EOD MV Day 2 = 100 shares * $105/share = 10500
    poll_db_until(
        query="SELECT eod_market_value FROM portfolio_timeseries WHERE portfolio_id = :pid AND date = :date",
        params={"pid": portfolio_id, "date": date(2025, 3, 11)},
        validation_func=lambda r: r is not None and r.eod_market_value == Decimal("10500.0000000000"),
        timeout=120,
        fail_message="Pipeline did not generate portfolio_timeseries for Day 2."
    )
    
    return {"portfolio_id": portfolio_id}

def test_advanced_performance_api(setup_performance_data, e2e_api_client: E2EApiClient):
    """
    Tests the full pipeline by calling the new on-the-fly performance endpoint
    with a request for multiple, complex period types.
    """
    # ARRANGE
    portfolio_id = setup_performance_data["portfolio_id"]
    api_url = f"/portfolios/{portfolio_id}/performance"
    
    # --- Manual Expected Calculations ---
    # Day 1 (Mar 10) RoR: (EOD_MV:10200 - BOD_MV:0 - BOD_CF:10000) / (BOD_MV:0 + BOD_CF:10000) = 2.0%
    # Day 2 (Mar 11) RoR: (EOD_MV:10500 - BOD_MV:10200) / BOD_MV:10200 = 2.941176%
    # Total Linked Return = ((1 + 0.02) * (1 + 0.02941176)) - 1 = 0.0500... => 5.0%
    
    request_payload = {
        "scope": {
            "as_of_date": "2025-03-11",
            "net_or_gross": "NET"
        },
        "periods": [
            { "name": "Month To Date", "type": "MTD" },
            { 
              "name": "SpecificRange",
              "type": "EXPLICIT",
              "from": "2025-03-10",
              "to": "2025-03-11"
            }
        ],
        "options": { "include_cumulative": True, "include_annualized": False }
    }
    
    # ACT
    response = e2e_api_client.post_query(api_url, request_payload)
    data = response.json()
    
    # ASSERT
    assert response.status_code == 200
    assert data["scope"]["net_or_gross"] == "NET"
    assert "Month To Date" in data["summary"]
    assert "SpecificRange" in data["summary"]
    
    # Both periods cover the same underlying data, so their return should be identical.
    assert pytest.approx(data["summary"]["Month To Date"]["cumulative_return"], abs=1e-4) == 5.0
    assert pytest.approx(data["summary"]["SpecificRange"]["cumulative_return"], abs=1e-4) == 5.0