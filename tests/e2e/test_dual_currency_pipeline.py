# tests/e2e/test_dual_currency_pipeline.py
import pytest
import requests
import time
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text

# The api_endpoints and poll_for_data fixtures are now imported from conftest

@pytest.fixture(scope="module")
def setup_dual_currency_data(docker_services, db_engine, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that cleans the DB and ingests a full dual-currency trade scenario.
    It waits until the final position is fully calculated and valued before yielding.
    """
    # --- Clean the database once for this module ---
    TABLES = [
        "portfolio_valuation_jobs", "portfolio_aggregation_jobs", "transaction_costs", "cashflows", "position_history", "daily_position_snapshots",
        "position_timeseries", "portfolio_timeseries", "transactions", "market_prices",
        "instruments", "fx_rates", "portfolios", "processed_events", "outbox_events"
    ]
    truncate_query = text(f"TRUNCATE TABLE {', '.join(TABLES)} RESTART IDENTITY CASCADE;")
    with db_engine.begin() as connection:
        connection.execute(truncate_query)
    # --- End Cleaning ---

    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]
    portfolio_id = "E2E_DUAL_CURRENCY_01"
    security_id = "SEC_DAIMLER_DE"
    buy_date, sell_date = "2025-08-10", "2025-08-15"

    # 1. Ingest prerequisite reference data
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "DC_CIF", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": security_id, "name": "Daimler AG", "isin": "DE0007100000", "instrumentCurrency": "EUR", "productType": "Equity"}]})
    requests.post(f"{ingestion_url}/ingest/fx-rates", json={"fx_rates": [{"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": buy_date, "rate": "1.10"}, {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": sell_date, "rate": "1.20"}]})

    # 2. Ingest transactions
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [
        {"transaction_id": f"{security_id}_BUY", "portfolio_id": portfolio_id, "instrument_id": "DAI", "security_id": security_id, "transaction_date": f"{buy_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150.0, "gross_transaction_amount": 15000.0, "trade_currency": "EUR", "currency": "EUR"},
        {"transaction_id": f"{security_id}_SELL", "portfolio_id": portfolio_id, "instrument_id": "DAI", "security_id": security_id, "transaction_date": f"{sell_date}T10:00:00Z", "transaction_type": "SELL", "quantity": 40, "price": 170.0, "gross_transaction_amount": 6800.0, "trade_currency": "EUR", "currency": "EUR"}
    ]})
    
    # 3. Ingest market price for final valuation
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": sell_date, "price": 180.0, "currency": "EUR"}]})

    # 4. Poll until the final position is valued, ensuring the pipeline has completed
    pos_url = f'{query_url}/portfolios/{portfolio_id}/positions'
    pos_validation = lambda data: (
        data.get("positions") and len(data["positions"]) == 1 and
        data["positions"][0].get("valuation", {}).get("unrealized_gain_loss") is not None
    )
    poll_for_data(pos_url, pos_validation, timeout=120)
    
    return {"portfolio_id": portfolio_id, "query_url": query_url}

def test_realized_pnl_dual_currency(setup_dual_currency_data):
    """
    Verifies the realized P&L on the SELL transaction is calculated correctly in both currencies.
    """
    # ARRANGE
    portfolio_id = setup_dual_currency_data["portfolio_id"]
    query_url = setup_dual_currency_data["query_url"]
    tx_url = f'{query_url}/portfolios/{portfolio_id}/transactions'

    # ACT
    response = requests.get(tx_url)
    assert response.status_code == 200
    tx_data = response.json()

    sell_tx = tx_data["transactions"][0]
    assert sell_tx["transaction_type"] == "SELL"

    # ASSERT
    # Local P&L (EUR): (40 * 170) - (40 * 150) = 800 EUR
    assert Decimal(sell_tx["realized_gain_loss_local"]).quantize(Decimal("0.01")) == Decimal("800.00")
    
    # Base P&L (USD): (Proceeds in USD) - (Cost in USD)
    # Proceeds: 6800 EUR * 1.20 (sell date FX) = 8160 USD
    # Cost: (40 * 150 EUR) * 1.10 (buy date FX) = 6600 USD
    # P&L: 8160 - 6600 = 1560 USD
    assert Decimal(sell_tx["realized_gain_loss"]).quantize(Decimal("0.01")) == Decimal("1560.00")

def test_unrealized_pnl_dual_currency(setup_dual_currency_data):
    """
    Verifies the cost basis and unrealized P&L on the final open position.
    """
    # ARRANGE
    portfolio_id = setup_dual_currency_data["portfolio_id"]
    query_url = setup_dual_currency_data["query_url"]
    pos_url = f'{query_url}/portfolios/{portfolio_id}/positions'

    # ACT
    response = requests.get(pos_url)
    assert response.status_code == 200
    pos_data = response.json()
    position = pos_data["positions"][0]
    valuation = position["valuation"]

    # ASSERT
    # Cost Basis (60 shares):
    # Local: 60 * 150 EUR = 9000 EUR
    assert Decimal(position["cost_basis_local"]).quantize(Decimal("0.01")) == Decimal("9000.00")
    # Base: 9000 EUR * 1.10 (buy date FX) = 9900 USD
    assert Decimal(position["cost_basis"]).quantize(Decimal("0.01")) == Decimal("9900.00")

    # Valuation (60 shares @ 180 EUR/share):
    # Local: 60 * 180 EUR = 10800 EUR
    assert Decimal(valuation["market_value_local"]).quantize(Decimal("0.01")) == Decimal("10800.00")
    # Base: 10800 EUR * 1.20 (sell date FX) = 12960 USD
    assert Decimal(valuation["market_value"]).quantize(Decimal("0.01")) == Decimal("12960.00")

    # Unrealized P&L:
    # Local: 10800 (MV) - 9000 (Cost) = 1800 EUR
    assert Decimal(valuation["unrealized_gain_loss_local"]).quantize(Decimal("0.01")) == Decimal("1800.00")
    # Base: 12960 (MV) - 9900 (Cost) = 3060 USD
    assert Decimal(valuation["unrealized_gain_loss"]).quantize(Decimal("0.01")) == Decimal("3060.00")