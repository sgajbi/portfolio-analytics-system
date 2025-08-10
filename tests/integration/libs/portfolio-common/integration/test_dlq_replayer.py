# libs/portfolio-common/tests/integration/test_dlq_replayer.py
import pytest
import asyncio
import json
import uuid
import os
from unittest.mock import MagicMock, patch

from portfolio_common.kafka_utils import KafkaProducer
from tools.dlq_replayer import DLQReplayConsumer
# Import the actual DLQ topic from the application's config
from portfolio_common.config import KAFKA_PERSISTENCE_DLQ_TOPIC

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
    # Define the correct Kafka address for the host machine
    kafka_bootstrap_host = "localhost:9092"

    # 1. Define the original message that supposedly failed
    original_topic = "raw_transactions"
    original_key = f"txn-{uuid.uuid4()}"
    original_value = {"transaction_id": original_key, "amount": 1000}
    correlation_id = f"corr-{uuid.uuid4()}"

    # 2. Define the DLQ message structure that wraps the original message
    # FIX: Use the real DLQ topic configured for the application
    dlq_topic = KAFKA_PERSISTENCE_DLQ_TOPIC
    dlq_payload = {
        "original_topic": original_topic,
        "original_key": original_key,
        "original_value": json.dumps(original_value), # Original value is a stringified JSON
        "error_reason": "Test-induced failure",
        "correlation_id": correlation_id
    }

    # 3. Use a real producer to publish this message to the test DLQ topic
    setup_producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_host)
    setup_producer.publish_message(
        topic=dlq_topic,
        key="dlq_test_key",
        value=dlq_payload,
        headers=[('correlation_id', correlation_id.encode('utf-8'))]
    )
    setup_producer.flush()
    await asyncio.sleep(2) # Give Kafka a moment to process the message

    # ACT
    # 4. Patch `get_kafka_producer` so the consumer uses our MOCK producer for replaying
    with patch('tools.dlq_replayer.get_kafka_producer', return_value=mock_kafka_producer):
        consumer = DLQReplayConsumer(
            bootstrap_servers=kafka_bootstrap_host,
            topic=dlq_topic,
            group_id=f"test-replayer-group-{uuid.uuid4()}", # Unique group to read from start
            limit=1
        )
        await consumer.run()

    # ASSERT
    # 5. Verify the mock producer was called with the original message details
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    
    assert call_args["topic"] == original_topic
    assert call_args["key"] == original_key
    assert call_args["value"] == original_value # Should be the parsed dictionary
    assert ("correlation_id", correlation_id.encode("utf-8")) in call_args["headers"]