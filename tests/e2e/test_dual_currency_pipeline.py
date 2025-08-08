# tests/e2e/test_dual_currency_pipeline.py
import pytest
import requests
import time
import uuid
from decimal import Decimal

@pytest.fixture(scope="module")
def api_endpoints(docker_services):
    """Provides the URLs for the ingestion and query services."""
    ingestion_host = docker_services.get_service_host("ingestion-service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion-service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"

    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)
    query_url = f"http://{query_host}:{query_port}"
    
    return {"ingestion": ingestion_url, "query": query_url}

def poll_for_data(url: str, validation_func, timeout: int = 60):
    """Generic polling function to query an endpoint until a condition is met."""
    start_time = time.time()
    last_response_data = None
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                last_response_data = response.json()
                if validation_func(last_response_data):
                    return last_response_data
        except requests.ConnectionError:
            pass 
        time.sleep(2)
    
    pytest.fail(f"Polling timed out after {timeout} seconds for URL {url}. Last response: {last_response_data}")


def test_dual_currency_pnl_pipeline(api_endpoints, clean_db):
    """
    Tests the full end-to-end pipeline for a cross-currency trade,
    validating both realized and unrealized PnL attribution.
    """
    # ARRANGE
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = f"DUAL_CURRENCY_PORT_{uuid.uuid4()}"
    security_id = f"SEC_DAI_DE_{uuid.uuid4()}" # Daimler, trades in EUR
    buy_date, sell_date = "2025-08-10", "2025-08-15"

    # 1. Ingest all prerequisite data
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "DC_CIF", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": security_id, "name": "Daimler AG", "isin": "DE0007100000", "instrumentCurrency": "EUR", "productType": "Equity"}]})
    requests.post(f"{ingestion_url}/ingest/fx-rates", json={"fx_rates": [
        {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": buy_date, "rate": "1.10"},
        {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": sell_date, "rate": "1.20"}
    ]})

    # 2. Ingest transactions
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [
        {"transaction_id": f"{security_id}_BUY", "portfolio_id": portfolio_id, "instrument_id": "DAI", "security_id": security_id, "transaction_date": f"{buy_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150.0, "gross_transaction_amount": 15000.0, "trade_currency": "EUR", "currency": "EUR"},
        {"transaction_id": f"{security_id}_SELL", "portfolio_id": portfolio_id, "instrument_id": "DAI", "security_id": security_id, "transaction_date": f"{sell_date}T10:00:00Z", "transaction_type": "SELL", "quantity": 40, "price": 170.0, "gross_transaction_amount": 6800.0, "trade_currency": "EUR", "currency": "EUR"}
    ]})
    
    # 3. Ingest final market price
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": sell_date, "price": 180.0, "currency": "EUR"}]})

    # ACT & ASSERT (Part 1): Verify Realized PnL on the transaction query
    tx_url = f'{api_endpoints["query"]}/portfolios/{portfolio_id}/transactions'
    tx_validation = lambda data: data.get("transactions") and len(data["transactions"]) == 2 and data["transactions"][0].get("realized_gain_loss") is not None
    tx_data = poll_for_data(tx_url, tx_validation)
    
    sell_tx = tx_data["transactions"][0] # Default sort is date desc
    assert sell_tx["transaction_id"] == f"{security_id}_SELL"
    # Local PnL: (40 * 170) - (40 * 150) = 6800 - 6000 = 800 EUR
    assert Decimal(sell_tx["realized_gain_loss_local"]).quantize(Decimal("0.01")) == Decimal("800.00")
    # Base PnL: (6800 * 1.20) - (6000 * 1.10) = 8160 - 6600 = 1560 USD
    assert Decimal(sell_tx["realized_gain_loss"]).quantize(Decimal("0.01")) == Decimal("1560.00")

    # ACT & ASSERT (Part 2): Verify Unrealized PnL on the final position
    pos_url = f'{api_endpoints["query"]}/portfolios/{portfolio_id}/positions'
    pos_validation = lambda data: data.get("positions") and len(data["positions"]) == 1 and data["positions"][0].get("valuation", {}).get("unrealized_gain_loss") is not None
    pos_data = poll_for_data(pos_url, pos_validation)

    position = pos_data["positions"][0]
    # Remaining cost basis: 60 shares * 150 EUR/share = 9000 EUR
    assert Decimal(position["cost_basis_local"]).quantize(Decimal("0.01")) == Decimal("9000.00")
    # Remaining cost basis in base: 60 shares * (150 * 1.10) USD/share = 9900 USD
    assert Decimal(position["cost_basis"]).quantize(Decimal("0.01")) == Decimal("9900.00")

    valuation = position["valuation"]
    # Market Value Local: 60 shares * 180 EUR/share = 10800 EUR
    assert Decimal(valuation["market_value_local"]).quantize(Decimal("0.01")) == Decimal("10800.00")
    # Market Value Base: 10800 EUR * 1.20 FX = 12960 USD
    assert Decimal(valuation["market_value"]).quantize(Decimal("0.01")) == Decimal("12960.00")

    # Unrealized PnL Local: 10800 - 9000 = 1800 EUR
    assert Decimal(valuation["unrealized_gain_loss_local"]).quantize(Decimal("0.01")) == Decimal("1800.00")
    # Unrealized PnL Base: 12960 - 9900 = 3060 USD
    assert Decimal(valuation["unrealized_gain_loss"]).quantize(Decimal("0.01")) == Decimal("3060.00")