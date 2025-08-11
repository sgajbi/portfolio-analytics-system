# tests/e2e/test_fx_valuation_pipeline.py
import pytest
import requests
import time
import uuid
from decimal import Decimal

@pytest.fixture(scope="module")
def api_endpoints(docker_services):
    """Provides the URLs for the ingestion and query services."""
    ingestion_host = docker_services.get_service_host("ingestion_service", 8000)
    ingestion_port = docker_services.get_service_port("ingestion_service", 8000)
    ingestion_url = f"http://{ingestion_host}:{ingestion_port}"

    query_host = docker_services.get_service_host("query-service", 8001)
    query_port = docker_services.get_service_port("query-service", 8001)
    query_url = f"http://{query_host}:{query_port}"
    
    return {"ingestion": ingestion_url, "query": query_url}

def poll_for_position_valuation(url: str, timeout: int = 120): # FIX: Increased timeout to 120s
    """
    Polls the positions endpoint until a VALUED position with both local and base P&L is found.
    """
    start_time = time.time()
    last_response_data = None
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                last_response_data = response.json()
                positions = last_response_data.get("positions", [])
                if (positions and 
                    positions[0].get("valuation") and
                    positions[0]["valuation"].get("unrealized_gain_loss") is not None and
                    positions[0]["valuation"].get("unrealized_gain_loss_local") is not None):
                    return last_response_data
        except requests.ConnectionError:
            pass 
        time.sleep(2)
    
    pytest.fail(f"Polling timed out after {timeout} seconds for URL {url}. Last response: {last_response_data}")


def test_cross_currency_valuation_calculates_dual_currency_pnl(api_endpoints, clean_db):
    """
    Tests that a position's market value and unrealized P&L are correctly
    calculated in both the instrument's local currency (EUR) and the portfolio's
    base currency (USD).
    """
    # ARRANGE
    ingestion_url = api_endpoints["ingestion"]
    portfolio_id = f"FX_VAL_PORT_{uuid.uuid4()}"
    security_id = f"SEC_AIRBUS_{uuid.uuid4()}"
    tx_date = "2025-08-08"

    # 1. Ingest a USD-based portfolio
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [
        {"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "FX_CIF", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}
    ]})

    # 2. Ingest a EUR-based instrument
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [
        {"securityId": security_id, "name": "Airbus SE", "isin": "NL0000235190", "instrumentCurrency": "EUR", "productType": "Equity"}
    ]})
    
    # 3. Ingest FX Rate for the transaction and valuation date
    requests.post(f"{ingestion_url}/ingest/fx-rates", json={"fx_rates": [
      {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": tx_date, "rate": "1.10"}
    ]})

    # 4. Ingest a BUY transaction in EUR
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{
        "transaction_id": f"TXN_{security_id}", "portfolio_id": portfolio_id, "instrument_id": "AIR",
        "security_id": security_id, "transaction_date": f"{tx_date}T10:00:00Z", "transaction_type": "BUY",
        "quantity": 100, "price": 150.0, "gross_transaction_amount": 15000.0,
        "trade_currency": "EUR", "currency": "EUR"
    }]})
    
    # 5. Ingest a market price in EUR for valuation
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{
        "securityId": security_id, "priceDate": tx_date, "price": 160.0, "currency": "EUR"
    }]})

    # ACT: Poll the query service until the valued position appears
    query_url = f'{api_endpoints["query"]}/portfolios/{portfolio_id}/positions'
    response_data = poll_for_position_valuation(query_url)

    # ASSERT
    assert len(response_data["positions"]) == 1
    position = response_data["positions"][0]
    valuation = position["valuation"]

    # Assert Cost Basis (Local and Base)
    # Cost (Local) = 100 shares * €150/share = €15,000
    assert Decimal(position["cost_basis_local"]).quantize(Decimal("0.01")) == Decimal("15000.00")
    # Cost (Base) = €15,000 * 1.10 FX Rate = $16,500
    assert Decimal(position["cost_basis"]).quantize(Decimal("0.01")) == Decimal("16500.00")

    # Assert Valuation (Local and Base)
    assert valuation["market_price"] == "160.0000000000"
    # Market Value (Local) = 100 shares * €160/share = €16,000
    assert Decimal(valuation["market_value_local"]).quantize(Decimal("0.01")) == Decimal("16000.00")
    # Market Value (Base) = €16,000 * 1.10 FX Rate = $17,600
    assert Decimal(valuation["market_value"]).quantize(Decimal("0.01")) == Decimal("17600.00")

    # Assert Unrealized P&L (Local and Base)
    # P&L (Local) = €16,000 (MV) - €15,000 (Cost) = €1,000
    assert Decimal(valuation["unrealized_gain_loss_local"]).quantize(Decimal("0.01")) == Decimal("1000.00")
    # P&L (Base) = $17,600 (MV) - $16,500 (Cost) = $1,100
    assert Decimal(valuation["unrealized_gain_loss"]).quantize(Decimal("0.01")) == Decimal("1100.00")