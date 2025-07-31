# services/ingestion-service/tests/integration/test_transaction_router.py
import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock
from datetime import datetime

from portfolio_common.config import KAFKA_RAW_TRANSACTIONS_TOPIC

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio


async def test_ingest_transactions_success(
    test_client: AsyncClient, mock_kafka_producer: MagicMock
):
    """
    GIVEN a valid list of transactions
    WHEN the /ingest/transactions endpoint is called
    THEN it should return a 202 Accepted status
    AND call the kafka producer's publish_message method for each transaction
    """
    # GIVEN
    transaction_payload = {
        "transactions": [
            {
                "transaction_id": "INT_TEST_001",
                "portfolio_id": "PORT_INT_01",
                "instrument_id": "AAPL",
                "security_id": "SEC_AAPL",
                "transaction_date": "2025-07-31T10:00:00Z",
                "transaction_type": "BUY",
                "quantity": 10.0,
                "price": 150.0,
                "gross_transaction_amount": 1500.0,
                "trade_currency": "USD",
                "currency": "USD",
            }
        ]
    }

    # WHEN
    response = await test_client.post("/ingest/transactions", json=transaction_payload)

    # THEN
    assert response.status_code == 202
    assert response.json() == {
        "message": "Successfully queued 1 transactions for processing."
    }

    # Verify that the kafka producer was called correctly
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args

    assert call_args.kwargs["topic"] == KAFKA_RAW_TRANSACTIONS_TOPIC
    assert call_args.kwargs["key"] == "INT_TEST_001"
    
    # Check the content of the published message
    published_value = call_args.kwargs["value"]
    assert published_value["transaction_id"] == "INT_TEST_001"
    assert published_value["portfolio_id"] == "PORT_INT_01"