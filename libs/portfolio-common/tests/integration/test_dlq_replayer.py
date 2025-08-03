# libs/portfolio-common/tests/integration/test_dlq_replayer.py
import pytest
import asyncio
import json
import uuid
import os
from unittest.mock import MagicMock, patch

from portfolio_common.kafka_utils import get_kafka_producer
from tools.dlq_replayer import DLQReplayConsumer

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock of the KafkaProducer for the replayer to use."""
    mock = MagicMock()
    mock.publish_message = MagicMock()
    mock.flush = MagicMock()
    return mock

async def test_dlq_replayer_consumes_and_republishes(docker_services, mock_kafka_producer):
    """
    GIVEN a message in a DLQ topic
    WHEN the DLQReplayConsumer runs
    THEN it should parse the message and republish it to the original topic.
    """
    # ARRANGE
    # 1. Define the original message that supposedly failed
    original_topic = "raw_transactions"
    original_key = f"txn-{uuid.uuid4()}"
    original_value = {"transaction_id": original_key, "amount": 1000}
    correlation_id = f"corr-{uuid.uuid4()}"

    # 2. Define the DLQ message structure that wraps the original message
    dlq_topic = "test_persistence.dlq"
    dlq_payload = {
        "original_topic": original_topic,
        "original_key": original_key,
        "original_value": json.dumps(original_value), # Original value is a stringified JSON
        "error_reason": "Test-induced failure",
        "correlation_id": correlation_id
    }

    # 3. Use a real producer to publish this message to the test DLQ topic
    # This producer is separate from the mock one used for assertions
    setup_producer = get_kafka_producer()
    setup_producer.publish_message(
        topic=dlq_topic,
        key="dlq_test_key",
        value=dlq_payload,
        headers=[('correlation_id', correlation_id.encode('utf-8'))]
    )
    setup_producer.flush()

    # ACT
    # 4. Patch `get_kafka_producer` so the consumer uses our MOCK producer
    with patch('tools.dlq_replayer.get_kafka_producer', return_value=mock_kafka_producer):
        # Instantiate the consumer to process just one message from our test DLQ
        consumer = DLQReplayConsumer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9093"),
            topic=dlq_topic,
            group_id=f"test-replayer-group-{uuid.uuid4()}", # Unique group to read from start
            limit=1
        )
        
        # Run the consumer until it hits the limit and stops
        await consumer.run()

    # ASSERT
    # 5. Verify the mock producer was called with the original message details
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    
    assert call_args["topic"] == original_topic
    assert call_args["key"] == original_key
    assert call_args["value"] == original_value # Should be the parsed dictionary
    assert ("correlation_id", correlation_id.encode("utf-8")) in call_args["headers"]