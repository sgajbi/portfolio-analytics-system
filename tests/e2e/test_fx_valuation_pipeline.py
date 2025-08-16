# tests/e2e/test_fx_valuation_pipeline.py
import pytest
import requests
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.orm import Session

@pytest.fixture(scope="module")
def setup_fx_valuation_data(docker_services, db_engine, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that cleans the DB, ingests data for a cross-currency
    valuation scenario, and waits for the calculation to complete.
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
    portfolio_id = "E2E_FX_VAL_PORT_01"
    security_id = "SEC_AIRBUS_FX"
    tx_date = "2025-08-08"

    # 1. Ingest a USD-based portfolio
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "FX_CIF", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]})
    # 2. Ingest a EUR-based instrument
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [{"securityId": security_id, "name": "Airbus SE", "isin": "NL0000235190", "instrumentCurrency": "EUR", "productType": "Equity"}]})
    # 3. Ingest FX Rate for the transaction and valuation date
    requests.post(f"{ingestion_url}/ingest/fx-rates", json={"fx_rates": [{"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": tx_date, "rate": "1.10"}]})
    # 4. Ingest a BUY transaction in EUR
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": f"TXN_{security_id}", "portfolio_id": portfolio_id, "instrument_id": "AIR", "security_id": security_id, "transaction_date": f"{tx_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150.0, "gross_transaction_amount": 15000.0, "trade_currency": "EUR", "currency": "EUR"}]})
    # 5. Ingest a market price in EUR for valuation
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": tx_date, "price": 160.0, "currency": "EUR"}]})

    # 6. Poll until the final position is valued
    poll_url = f'{query_url}/portfolios/{portfolio_id}/positions'
    validation_func = lambda data: (
        data.get("positions") and len(data["positions"]) == 1 and
        data["positions"][0].get("valuation", {}).get("unrealized_gain_loss") is not None
    )
    poll_for_data(poll_url, validation_func, timeout=60)
    
    return {"portfolio_id": portfolio_id, "query_url": query_url}


def test_cross_currency_valuation_calculates_dual_currency_pnl(setup_fx_valuation_data):
    """
    Tests that a position's market value and unrealized P&L are correctly
    calculated in both the instrument's local currency (EUR) and the portfolio's
    base currency (USD).
    """
    # ARRANGE
    portfolio_id = setup_fx_valuation_data["portfolio_id"]
    query_url = setup_fx_valuation_data["query_url"]
    pos_url = f'{query_url}/portfolios/{portfolio_id}/positions'

    # ACT
    response = requests.get(pos_url)
    assert response.status_code == 200
    response_data = response.json()

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