# tests/e2e/test_dual_currency_workflow.py
import pytest
from decimal import Decimal
from .api_client import E2EApiClient

@pytest.fixture(scope="module")
def setup_dual_currency_data(clean_db_module, e2e_api_client: E2EApiClient):
    """
    A module-scoped fixture that ingests a full dual-currency trade scenario.
    It waits until the final position is fully calculated and valued before yielding.
    """
    portfolio_id = "E2E_DUAL_CURRENCY_01"
    security_id = "SEC_DAIMLER_DE"
    buy_date, sell_date = "2025-08-10", "2025-08-15"

    # 1. Ingest prerequisite reference data
    e2e_api_client.ingest("/ingest/portfolios", {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2025-01-01", "cifId": "DC_CIF", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]})
    e2e_api_client.ingest("/ingest/instruments", {"instruments": [{"securityId": security_id, "name": "Daimler AG", "isin": "DE0007100000", "instrumentCurrency": "EUR", "productType": "Equity"}]})
    e2e_api_client.ingest("/ingest/fx-rates", {"fx_rates": [{"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": buy_date, "rate": "1.10"}, {"fromCurrency": "EUR", "toCurrency": "USD", "rateDate": sell_date, "rate": "1.20"}]})
    e2e_api_client.ingest("/ingest/business-dates", {"business_dates": [{"businessDate": buy_date}, {"businessDate": sell_date}]})

    # 2. Ingest transactions
    e2e_api_client.ingest("/ingest/transactions", {"transactions": [
        {"transaction_id": f"{security_id}_BUY", "portfolio_id": portfolio_id, "instrument_id": "DAI", "security_id": security_id, "transaction_date": f"{buy_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 150.0, "gross_transaction_amount": 15000.0, "trade_currency": "EUR", "currency": "EUR"},
        {"transaction_id": f"{security_id}_SELL", "portfolio_id": portfolio_id, "instrument_id": "DAI", "security_id": security_id, "transaction_date": f"{sell_date}T10:00:00Z", "transaction_type": "SELL", "quantity": 40, "price": 170.0, "gross_transaction_amount": 6800.0, "trade_currency": "EUR", "currency": "EUR"}
    ]})
    
    # 3. Ingest market price for final valuation
    e2e_api_client.ingest("/ingest/market-prices", {"market_prices": [{"securityId": security_id, "priceDate": sell_date, "price": 180.0, "currency": "EUR"}]})

    # 4. Poll until the final position is valued, ensuring the pipeline has completed
    pos_url = f'/portfolios/{portfolio_id}/positions'
    pos_validation = lambda data: (
        data.get("positions") and len(data["positions"]) == 1 and
        data["positions"][0].get("valuation", {}).get("unrealized_gain_loss") is not None
    )
    e2e_api_client.poll_for_data(pos_url, pos_validation, timeout=120)
    
    return {"portfolio_id": portfolio_id}

def test_realized_pnl_dual_currency(setup_dual_currency_data, e2e_api_client: E2EApiClient):
    """
    Verifies the realized P&L on the SELL transaction is calculated correctly in both currencies.
    """
    # ARRANGE
    portfolio_id = setup_dual_currency_data["portfolio_id"]
    tx_url = f'/portfolios/{portfolio_id}/transactions'

    # ACT
    response = e2e_api_client.query(tx_url)
    tx_data = response.json()

    sell_tx = next(t for t in tx_data["transactions"] if t["transaction_type"] == "SELL")

    # ASSERT
    # Local P&L (EUR): (40 * 170) - (40 * 150) = 800 EUR
    assert sell_tx["realized_gain_loss_local"] == pytest.approx(800.00)
    
    # Base P&L (USD): (Proceeds in USD) - (Cost in USD)
    # Proceeds: 6800 EUR * 1.20 (sell date FX) = 8160 USD
    # Cost: (40 * 150 EUR) * 1.10 (buy date FX) = 6600 USD
    # P&L: 8160 - 6600 = 1560 USD
    assert sell_tx["realized_gain_loss"] == pytest.approx(1560.00)

def test_unrealized_pnl_dual_currency(setup_dual_currency_data, e2e_api_client: E2EApiClient):
    """
    Verifies the cost basis and unrealized P&L on the final open position.
    """
    # ARRANGE
    portfolio_id = setup_dual_currency_data["portfolio_id"]
    pos_url = f'/portfolios/{portfolio_id}/positions'

    # ACT
    response = e2e_api_client.query(pos_url)
    pos_data = response.json()
    position = pos_data["positions"][0]
    valuation = position["valuation"]

    # ASSERT
    # Cost Basis (60 shares):
    # Local: 60 * 150 EUR = 9000 EUR
    assert position["cost_basis_local"] == pytest.approx(9000.00)
    # Base: 9000 EUR * 1.10 (buy date FX) = 9900 USD
    assert position["cost_basis"] == pytest.approx(9900.00)

    # Valuation (60 shares @ 180 EUR/share):
    # Local: 60 * 180 EUR = 10800 EUR
    assert valuation["market_value_local"] == pytest.approx(10800.00)
    # Base: 10800 EUR * 1.20 (sell date FX) = 12960 USD
    assert valuation["market_value"] == pytest.approx(12960.00)

    # Unrealized P&L:
    # Local: 10800 (MV) - 9000 (Cost) = 1800 EUR
    assert valuation["unrealized_gain_loss_local"] == pytest.approx(1800.00)
    # Base: 12960 (MV) - 9900 (Cost) = 3060 USD
    assert valuation["unrealized_gain_loss"] == pytest.approx(3060.00)