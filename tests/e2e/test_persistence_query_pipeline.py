# tests/e2e/test_persistence_query_pipeline.py
import pytest
import requests
from datetime import date
from sqlalchemy import text
from sqlalchemy.orm import Session

@pytest.fixture(scope="module")
def setup_persistence_data(clean_db_module, api_endpoints, poll_for_data):
    """
    A module-scoped fixture that ingests a comprehensive set of data and waits for it all to be queryable.
    """
    ingestion_url = api_endpoints["ingestion"]
    query_url = api_endpoints["query"]
    
    # Define all identifiers
    portfolio_id = "E2E_PQ_PORT_01"
    security_id = "SEC_PQ_INST_01"
    transaction_id = "TXN_PQ_01"
    price_date = date.today().isoformat()
    
    # Ingest one of each entity type
    requests.post(f"{ingestion_url}/ingest/portfolios", json={"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "SGD", "openDate": "2024-01-01", "cifId": "CIF_PQ_1", "status": "ACTIVE", "riskExposure":"a", "investmentTimeHorizon":"b", "portfolioType":"c", "bookingCenter":"d"}]})
    requests.post(f"{ingestion_url}/ingest/instruments", json={"instruments": [
        {"securityId": security_id, "name": "Test Instrument PQ", "isin": f"ISIN_{security_id}", "instrumentCurrency": "USD", "productType": "Equity"},
        {"securityId": "SEC_NO_PRICE", "name": "Unpriced Instrument", "isin": "ISIN_NO_PRICE", "instrumentCurrency": "USD", "productType": "Equity"}
    ]})
    requests.post(f"{ingestion_url}/ingest/market-prices", json={"market_prices": [{"securityId": security_id, "priceDate": price_date, "price": 123.45, "currency": "HKD"}]})
    requests.post(f"{ingestion_url}/ingest/fx-rates", json={"fx_rates": [{"fromCurrency": "USD", "toCurrency": "EUR", "rateDate": price_date, "rate": 0.95}]})
    requests.post(f"{ingestion_url}/ingest/transactions", json={"transactions": [{"transaction_id": transaction_id, "portfolio_id": portfolio_id, "instrument_id": "TEST", "security_id": security_id, "transaction_date": f"{price_date}T10:00:00Z", "transaction_type": "BUY", "quantity": 100, "price": 10, "gross_transaction_amount": 1000, "trade_currency": "USD", "currency": "USD"}]})

    # Poll all endpoints to ensure data is ready before tests run
    poll_for_data(f"{query_url}/portfolios?portfolio_id={portfolio_id}", lambda data: data.get("portfolios") and len(data["portfolios"]) == 1)
    poll_for_data(f"{query_url}/instruments?security_id={security_id}", lambda data: data.get("instruments") and len(data["instruments"]) == 1)
    poll_for_data(f"{query_url}/prices?security_id={security_id}", lambda data: data.get("prices") and len(data["prices"]) == 1)
    poll_for_data(f"{query_url}/fx-rates?from_currency=USD&to_currency=EUR", lambda data: data.get("rates") and len(data["rates"]) == 1)
    poll_for_data(f"{query_url}/portfolios/{portfolio_id}/transactions", lambda data: data.get("transactions") and len(data["transactions"]) == 1)

    return {"query_url": query_url, "portfolio_id": portfolio_id, "security_id": security_id, "transaction_id": transaction_id, "price_date": price_date}

def test_portfolio_query(setup_persistence_data):
    """Tests that the ingested portfolio can be queried correctly."""
    api_response = requests.get(f"{setup_persistence_data['query_url']}/portfolios?portfolio_id={setup_persistence_data['portfolio_id']}")
    assert api_response.status_code == 200
    data = api_response.json()["portfolios"][0]
    assert data["portfolio_id"] == setup_persistence_data["portfolio_id"]
    assert data["base_currency"] == "SGD"

def test_instrument_query(setup_persistence_data):
    """Tests that the ingested instrument can be queried correctly."""
    api_response = requests.get(f"{setup_persistence_data['query_url']}/instruments?security_id={setup_persistence_data['security_id']}")
    assert api_response.status_code == 200
    data = api_response.json()["instruments"][0]
    assert data["security_id"] == setup_persistence_data["security_id"]
    assert data["name"] == "Test Instrument PQ"

def test_market_price_query(setup_persistence_data):
    """Tests that the ingested market price can be queried correctly."""
    api_response = requests.get(f"{setup_persistence_data['query_url']}/prices?security_id={setup_persistence_data['security_id']}")
    assert api_response.status_code == 200
    data = api_response.json()["prices"][0]
    assert data["price_date"] == setup_persistence_data["price_date"]
    assert float(data["price"]) == 123.45

def test_fx_rate_query(setup_persistence_data):
    """Tests that the ingested FX rate can be queried correctly."""
    api_response = requests.get(f"{setup_persistence_data['query_url']}/fx-rates?from_currency=USD&to_currency=EUR")
    assert api_response.status_code == 200
    data = api_response.json()["rates"][0]
    assert data["rate_date"] == setup_persistence_data["price_date"]
    assert float(data["rate"]) == 0.95

def test_transaction_query(setup_persistence_data):
    """Tests that the ingested transaction can be queried correctly."""
    api_response = requests.get(f"{setup_persistence_data['query_url']}/portfolios/{setup_persistence_data['portfolio_id']}/transactions")
    assert api_response.status_code == 200
    data = api_response.json()["transactions"][0]
    assert data["transaction_id"] == setup_persistence_data["transaction_id"]
    assert float(data["quantity"]) == 100

def test_query_prices_for_unpriced_security_returns_empty_list(setup_persistence_data):
    """
    Tests that querying the /prices endpoint for a valid security that has
    no price data results in a 200 OK with an empty list.
    """
    # ARRANGE
    query_url = setup_persistence_data['query_url']
    security_id_with_no_price = "SEC_NO_PRICE"
    url = f"{query_url}/prices?security_id={security_id_with_no_price}"

    # ACT
    response = requests.get(url)

    # ASSERT
    assert response.status_code == 200
    data = response.json()
    assert data["security_id"] == security_id_with_no_price
    assert data["prices"] == []