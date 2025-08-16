# tests/e2e/test_reliability_pipeline.py
import pytest
import requests
import time
import uuid
from sqlalchemy.orm import Session
from sqlalchemy import text

def test_instrument_ingestion_is_idempotent(api_endpoints, clean_db, poll_for_data):
    """
    Tests that ingesting the same instrument twice results in only one record.
    """
    # ARRANGE
    ingestion_url = api_endpoints['ingestion']
    query_url = api_endpoints['query']
    security_id = f"SEC_IDEMPOTENT_{uuid.uuid4()}"
    ingest_payload = {"instruments": [{"securityId": security_id, "name": "Idempotent Test Instrument", "isin": f"ISIN_{uuid.uuid4()}", "instrumentCurrency": "JPY", "productType": "Future"}]}

    # ACT: Ingest the same payload twice
    assert requests.post(f"{ingestion_url}/ingest/instruments", json=ingest_payload).status_code == 202
    assert requests.post(f"{ingestion_url}/ingest/instruments", json=ingest_payload).status_code == 202

    # ASSERT: Poll and verify only one record exists
    poll_url = f"{query_url}/instruments?security_id={security_id}"
    validation_func = lambda data: data.get("instruments") and len(data["instruments"]) == 1
    query_data = poll_for_data(poll_url, validation_func)

    assert query_data["instruments"][0]["name"] == "Idempotent Test Instrument"

def test_portfolio_update_persistence(api_endpoints, clean_db, poll_for_data):
    """
    Tests that ingesting a portfolio with an existing ID updates the record.
    """
    # ARRANGE
    ingestion_url = api_endpoints['ingestion']
    query_url = api_endpoints['query']
    portfolio_id = f"E2E_UPDATE_PORT_{uuid.uuid4()}"
    initial_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "AUD", "status": "PENDING", "openDate": "2024-01-01", "cifId": "CIF_U_1", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}
    update_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "AUD", "status": "ACTIVE", "openDate": "2024-01-01", "cifId": "CIF_U_1", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}
    
    requests.post(f"{ingestion_url}/ingest/portfolios", json=initial_payload)
    poll_url = f"{query_url}/portfolios?portfolio_id={portfolio_id}"
    poll_for_data(poll_url, lambda data: data.get("portfolios") and data["portfolios"][0]["status"] == "PENDING")

    # ACT
    assert requests.post(f"{ingestion_url}/ingest/portfolios", json=update_payload).status_code == 202

    # ASSERT
    poll_for_data(poll_url, lambda data: data.get("portfolios") and data["portfolios"][0]["status"] == "ACTIVE")

def test_transaction_persists_after_portfolio_arrives(api_endpoints, clean_db, poll_for_data):
    """
    Tests that a transaction consumer retries and succeeds if the portfolio arrives late.
    """
    # ARRANGE
    ingestion_url = api_endpoints['ingestion']
    query_url = api_endpoints['query']
    portfolio_id = f"E2E_RETRY_PORT_{uuid.uuid4()}"
    transaction_id = f"TXN_RETRY_{uuid.uuid4()}"
    transaction_payload = {"transactions": [{"transaction_id": transaction_id, "portfolio_id": portfolio_id, "instrument_id": "RETRY", "security_id": "SEC_RETRY", "transaction_date": "2025-08-01T10:00:00Z", "transaction_type": "BUY", "quantity": 10, "price": 1, "gross_transaction_amount": 10, "trade_currency": "USD", "currency": "USD"}]}
    portfolio_payload = {"portfolios": [{"portfolioId": portfolio_id, "baseCurrency": "USD", "openDate": "2024-01-01", "cifId": "CIF_R_1", "status": "ACTIVE", "riskExposure": "a", "investmentTimeHorizon": "b", "portfolioType": "c", "bookingCenter": "d"}]}

    # ACT: Ingest the transaction first, then wait briefly before ingesting the portfolio it depends on.
    assert requests.post(f"{ingestion_url}/ingest/transactions", json=transaction_payload).status_code == 202
    time.sleep(2) 
    assert requests.post(f"{ingestion_url}/ingest/portfolios", json=portfolio_payload).status_code == 202

    # ASSERT: Poll for the transaction, which should now have been persisted.
    poll_url = f"{query_url}/portfolios/{portfolio_id}/transactions"
    validation_func = lambda data: data.get("transactions") and len(data["transactions"]) == 1
    query_data = poll_for_data(poll_url, validation_func)
    
    assert query_data["transactions"][0]["transaction_id"] == transaction_id