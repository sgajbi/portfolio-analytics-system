# tests/e2e/test_ingestion_service_api.py
import pytest
import requests

def test_ingest_empty_transaction_list_succeeds(api_endpoints):
    """
    GIVEN an empty list of transactions
    WHEN posting to the /ingest/transactions endpoint
    THEN the API should return a 202 Accepted response.
    """
    # ARRANGE
    ingestion_url = api_endpoints["ingestion"]
    payload = {"transactions": []}

    # ACT
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=payload)

    # ASSERT
    assert response.status_code == 202
    assert response.json() == {"message": "Successfully queued 0 transactions for processing."}

def test_ingest_malformed_transaction_payload_fails(api_endpoints):
    """
    GIVEN a malformed payload (not a JSON object with a 'transactions' key)
    WHEN posting to the /ingest/transactions endpoint
    THEN the API should return a 422 Unprocessable Entity response.
    """
    # ARRANGE
    ingestion_url = api_endpoints["ingestion"]
    # Payload is just a list, not a dictionary with the "transactions" key
    payload = [{"transaction_id": "bad-payload"}]

    # ACT
    response = requests.post(f"{ingestion_url}/ingest/transactions", json=payload)

    # ASSERT
    assert response.status_code == 422