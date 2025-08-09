import pytest
import requests
import time
import uuid
from datetime import date

# This fixture provides the base URLs for the services under test.
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

def poll_for_data(url: str, validation_func, timeout: int = 45):
    """
    Generic polling function to query an endpoint until a condition is met.
    
    Args:
        url: The API endpoint to poll.
        validation_func: A function that takes the response JSON and returns True if valid.
        timeout: The maximum time to wait in seconds.
    """
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
            pass # Service may not be ready, just continue polling
        time.sleep(1)
    
    pytest.fail(f"Polling timed out after {timeout} seconds for URL {url}. Last response: {last_response_data}")


def test_portfolio_persistence_and_query(api_endpoints, clean_db):
    """
    Tests that a portfolio can be ingested and then queried successfully.
    """
    # ARRANGE
    portfolio_id = f"E2E_PQ_PORT_{uuid.uuid4()}"
    ingest_payload = {"portfolios": [{
        "portfolioId": portfolio_id,
        "baseCurrency": "SGD",
        "openDate": "2024-01-01",
        "riskExposure": "Medium",
        "investmentTimeHorizon": "Long",
        "portfolioType": "Discretionary",
        "bookingCenter": "Singapore",
        "cifId": "CIF_PQ_1",
        "status": "ACTIVE"
    }]}

    # ACT: Ingest the data
    ingest_url = f"{api_endpoints['ingestion']}/ingest/portfolios"
    response = requests.post(ingest_url, json=ingest_payload)
    assert response.status_code == 202

    # ACT: Poll the query service until the data is available
    query_url = f"{api_endpoints['query']}/portfolios?portfolio_id={portfolio_id}"
    validation_func = lambda data: data.get("portfolios") and len(data["portfolios"]) == 1
    query_data = poll_for_data(query_url, validation_func)
    
    # ASSERT: Verify the queried data
    persisted_portfolio = query_data["portfolios"][0]
    assert persisted_portfolio["portfolio_id"] == portfolio_id
    assert persisted_portfolio["base_currency"] == "SGD"
    assert persisted_portfolio["booking_center"] == "Singapore"


def test_instrument_persistence_and_query(api_endpoints, clean_db):
    """
    Tests that an instrument can be ingested and then queried successfully.
    """
    # ARRANGE
    security_id = f"SEC_PQ_{uuid.uuid4()}"
    ingest_payload = {"instruments": [{
        "securityId": security_id,
        "name": "Test Instrument PQ",
        "isin": f"ISIN_{uuid.uuid4()}",
        "instrumentCurrency": "USD",
        "productType": "Equity"
    }]}

    # ACT: Ingest
    ingest_url = f"{api_endpoints['ingestion']}/ingest/instruments"
    response = requests.post(ingest_url, json=ingest_payload)
    assert response.status_code == 202

    # ACT: Poll & Query
    query_url = f"{api_endpoints['query']}/instruments?security_id={security_id}"
    validation_func = lambda data: data.get("instruments") and len(data["instruments"]) == 1
    query_data = poll_for_data(query_url, validation_func)

    # ASSERT
    persisted_instrument = query_data["instruments"][0]
    assert persisted_instrument["security_id"] == security_id
    assert persisted_instrument["name"] == "Test Instrument PQ"
    assert persisted_instrument["product_type"] == "Equity"


def test_market_price_persistence_and_query(api_endpoints, clean_db):
    """
    Tests that a market price can be ingested and then queried successfully.
    """
    # ARRANGE
    security_id = f"SEC_PQ_PRICE_{uuid.uuid4()}"
    price_date = date.today().isoformat()
    ingest_payload = {"market_prices": [{
        "securityId": security_id,
        "priceDate": price_date,
        "price": 123.45,
        "currency": "HKD"
    }]}

    # ACT: Ingest
    ingest_url = f"{api_endpoints['ingestion']}/ingest/market-prices"
    response = requests.post(ingest_url, json=ingest_payload)
    assert response.status_code == 202

    # ACT: Poll & Query
    query_url = f"{api_endpoints['query']}/prices?security_id={security_id}"
    validation_func = lambda data: data.get("prices") and len(data["prices"]) == 1
    query_data = poll_for_data(query_url, validation_func)

    # ASSERT
    persisted_price = query_data["prices"][0]
    assert query_data["security_id"] == security_id
    assert persisted_price["price_date"] == price_date
    assert float(persisted_price["price"]) == 123.45
    assert persisted_price["currency"] == "HKD"


def test_fx_rate_persistence_and_query(api_endpoints, clean_db):
    """
    Tests that an FX rate can be ingested and then queried successfully.
    """
    # ARRANGE
    rate_date = date.today().isoformat()
    ingest_payload = {"fx_rates": [{
        "fromCurrency": "USD",
        "toCurrency": "EUR",
        "rateDate": rate_date,
        "rate": 0.95
    }]}

    # ACT: Ingest
    ingest_url = f"{api_endpoints['ingestion']}/ingest/fx-rates"
    response = requests.post(ingest_url, json=ingest_payload)
    assert response.status_code == 202

    # ACT: Poll & Query
    query_url = f"{api_endpoints['query']}/fx-rates?from_currency=USD&to_currency=EUR"
    validation_func = lambda data: data.get("rates") and len(data["rates"]) == 1
    query_data = poll_for_data(query_url, validation_func)

    # ASSERT
    persisted_rate = query_data["rates"][0]
    assert query_data["from_currency"] == "USD"
    assert query_data["to_currency"] == "EUR"
    assert persisted_rate["rate_date"] == rate_date
    assert float(persisted_rate["rate"]) == 0.95


def test_transaction_persistence_and_query(api_endpoints, clean_db):
    """
    Tests that a transaction can be ingested and then queried successfully.
    Note: This only tests persistence, not calculated fields like cashflow.
    """
    # ARRANGE: Need to ingest the portfolio first to satisfy foreign key constraints
    portfolio_id = f"E2E_PQ_TRX_PORT_{uuid.uuid4()}"
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2024-01-01", "cifId": "CIF_PQ_2", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}
    ingest_port_url = f"{api_endpoints['ingestion']}/ingest/portfolios"
    requests.post(ingest_port_url, json=portfolio_payload)

    # Arrange transaction
    transaction_id = f"TXN_PQ_{uuid.uuid4()}"
    ingest_payload = {"transactions": [{
        "transaction_id": transaction_id,
        "portfolio_id": portfolio_id,
        "instrument_id": "TEST",
        "security_id": "SEC_TEST_PQ",
        "transaction_date": "2025-08-04T10:00:00Z",
        "transaction_type": "BUY",
        "quantity": 100,
        "price": 10,
        "gross_transaction_amount": 1000,
        "trade_currency": "USD",
        "currency": "USD"
    }]}

    # ACT: Ingest
    ingest_url = f"{api_endpoints['ingestion']}/ingest/transactions"
    response = requests.post(ingest_url, json=ingest_payload)
    assert response.status_code == 202

    # ACT: Poll & Query
    query_url = f"{api_endpoints['query']}/portfolios/{portfolio_id}/transactions"
    validation_func = lambda data: data.get("transactions") and len(data["transactions"]) == 1
    query_data = poll_for_data(query_url, validation_func)

    # ASSERT
    persisted_txn = query_data["transactions"][0]
    assert query_data["portfolio_id"] == portfolio_id
    assert persisted_txn["transaction_id"] == transaction_id
    assert persisted_txn["transaction_type"] == "BUY"
    assert float(persisted_txn["quantity"]) == 100


def test_instrument_ingestion_is_idempotent(api_endpoints, clean_db):
    """
    Tests that ingesting the same instrument twice results in only one record.
    """
    # ARRANGE
    security_id = f"SEC_IDEMPOTENT_{uuid.uuid4()}"
    ingest_payload = {"instruments": [{
        "securityId": security_id,
        "name": "Idempotent Test Instrument",
        "isin": f"ISIN_{uuid.uuid4()}",
        "instrumentCurrency": "JPY",
        "productType": "Future"
    }]}
    ingest_url = f"{api_endpoints['ingestion']}/ingest/instruments"

    # ACT: Ingest the same payload twice
    response1 = requests.post(ingest_url, json=ingest_payload)
    assert response1.status_code == 202
    response2 = requests.post(ingest_url, json=ingest_payload)
    assert response2.status_code == 202

    # ASSERT: Poll and verify only one record exists
    query_url = f"{api_endpoints['query']}/instruments?security_id={security_id}"
    validation_func = lambda data: data.get("instruments") and len(data["instruments"]) == 1
    query_data = poll_for_data(query_url, validation_func) # This will fail if more than 1 is created

    persisted_instrument = query_data["instruments"][0]
    assert persisted_instrument["name"] == "Idempotent Test Instrument"


def test_portfolio_update_persistence(api_endpoints, clean_db):
    """
    Tests that ingesting a portfolio with an existing ID updates the record.
    """
    # ARRANGE: Ingest the initial version
    portfolio_id = f"E2E_UPDATE_PORT_{uuid.uuid4()}"
    initial_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "AUD", "status": "PENDING", "openDate": "2024-01-01", "cifId": "CIF_U_1", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}
    update_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "AUD", "status": "ACTIVE", "openDate": "2024-01-01", "cifId": "CIF_U_1", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}
    
    ingest_url = f"{api_endpoints['ingestion']}/ingest/portfolios"
    requests.post(ingest_url, json=initial_payload)

    # Poll to ensure the first version is saved
    query_url = f"{api_endpoints['query']}/portfolios?portfolio_id={portfolio_id}"
    validation_func_initial = lambda data: data.get("portfolios") and data["portfolios"][0]["status"] == "PENDING"
    poll_for_data(query_url, validation_func_initial)

    # ACT: Ingest the updated version
    response = requests.post(ingest_url, json=update_payload)
    assert response.status_code == 202

    # ASSERT: Poll for the updated status
    validation_func_updated = lambda data: data.get("portfolios") and data["portfolios"][0]["status"] == "ACTIVE"
    query_data = poll_for_data(query_url, validation_func_updated)
    
    persisted_portfolio = query_data["portfolios"][0]
    assert persisted_portfolio["status"] == "ACTIVE"

def test_transaction_persists_after_portfolio_arrives(api_endpoints, clean_db):
    """
    Tests that a transaction consumer retries and succeeds if the portfolio arrives late.
    """
    # ARRANGE
    portfolio_id = f"E2E_RETRY_PORT_{uuid.uuid4()}"
    transaction_id = f"TXN_RETRY_{uuid.uuid4()}"

    transaction_payload = {"transactions": [{"transaction_id": transaction_id, "portfolio_id": portfolio_id, "instrument_id": "RETRY", "security_id": "SEC_RETRY", "transaction_date": "2025-08-01T10:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 1, "gross_transaction_amount": 10, "trade_currency": "USD", "currency": "USD"}]}
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2024-01-01", "cifId": "CIF_R_1", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}

    ingest_txn_url = f"{api_endpoints['ingestion']}/ingest/transactions"
    ingest_port_url = f"{api_endpoints['ingestion']}/ingest/portfolios"

    # ACT: Ingest the transaction first - this will force the consumer to wait
    response_txn = requests.post(ingest_txn_url, json=transaction_payload)
    assert response_txn.status_code == 202
    
    # Give it a second to fail once
    time.sleep(2) 

    # Now, ingest the portfolio it was waiting for
    response_port = requests.post(ingest_port_url, json=portfolio_payload)
    assert response_port.status_code == 202

    # ASSERT: Poll for the transaction, which should now have been persisted
    query_url = f"{api_endpoints['query']}/portfolios/{portfolio_id}/transactions"
    validation_func = lambda data: data.get("transactions") and len(data["transactions"]) == 1
    query_data = poll_for_data(query_url, validation_func)
    
    assert query_data["transactions"][0]["transaction_id"] == transaction_id

