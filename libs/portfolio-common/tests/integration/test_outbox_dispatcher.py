# libs/portfolio-common/tests/integration/test_outbox_dispatcher.py
import pytest
import asyncio
import json
import uuid
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from sqlalchemy import text, create_engine

from portfolio_common.database_models import OutboxEvent
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.outbox_dispatcher import OutboxDispatcher

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock of the KafkaProducer for testing."""
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    mock.flush = MagicMock()
    return mock

async def test_dispatcher_processes_and_updates_pending_events(
    db_engine, clean_db, mock_kafka_producer
):
    """
    GIVEN a pending event in the outbox_events table
    WHEN the OutboxDispatcher runs
    THEN it should publish the event to Kafka and update its status to PROCESSED.
    """
    # ARRANGE
    correlation_id = f"corr-id-{uuid.uuid4()}"
    aggregate_id = f"agg-id-{uuid.uuid4()}"
    event_payload = {"message": "hello world"}

    # Manually insert a PENDING event
    with Session(db_engine) as session:
        with session.begin():
            new_event = OutboxEvent(
                aggregate_type="TestAggregate",
                aggregate_id=aggregate_id,
                event_type="TestEvent",
                payload=json.dumps(event_payload),
                topic="test.topic",
                status="PENDING",
                correlation_id=correlation_id,
            )
            session.add(new_event)

    # Instantiate the dispatcher with the mock producer
    dispatcher = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)

    # ACT
    # Run the dispatcher for a short period to ensure it processes the batch
    dispatcher_task = asyncio.create_task(dispatcher.run())
    await asyncio.sleep(2) # Give it a moment to poll and process
    dispatcher.stop()
    await dispatcher_task

    # ASSERT
    # 1. Verify that the message was published to Kafka
    mock_kafka_producer.publish_message.assert_called_once()
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args["topic"] == "test.topic"
    assert call_args["key"] == aggregate_id
    assert call_args["value"] == event_payload
    assert ("correlation_id", correlation_id.encode("utf-8")) in call_args["headers"]
    
    # 2. Verify the event status is updated in the database
    with Session(db_engine) as session:
        query = text("SELECT status FROM outbox_events WHERE aggregate_id = :agg_id")
        result = session.execute(query, {"agg_id": aggregate_id}).scalar_one()
        assert result == "PROCESSED"

async def test_dispatcher_handles_kafka_publish_failure(
    db_engine, clean_db, mock_kafka_producer
):
    """
    GIVEN a pending event in the outbox
    WHEN the dispatcher runs but Kafka publishing fails
    THEN the event status should remain PENDING, and it should be processed on the next successful run.
    """
    # ARRANGE
    aggregate_id = f"agg-id-{uuid.uuid4()}"
    event_payload = {"message": "transient failure test"}
    
    with Session(db_engine) as session:
        with session.begin():
            session.add(OutboxEvent(
                aggregate_type="TestResilience",
                aggregate_id=aggregate_id,
                event_type="TestEvent",
                payload=json.dumps(event_payload),
                topic="resilience.topic",
                status="PENDING"
            ))

    # --- PHASE 1: Simulate Kafka Failure ---
    # Configure the mock producer to ALWAYS fail in this phase
    mock_kafka_producer.flush.side_effect = Exception("Kafka is down!")
    dispatcher_fail = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)

    # ACT 1: Run the dispatcher and stop it after one processing attempt
    task_fail = asyncio.create_task(dispatcher_fail.run())
    await asyncio.sleep(2) # Allow at least one poll cycle
    dispatcher_fail.stop()
    await task_fail

    # ASSERT 1: The event is still pending
    with Session(db_engine) as session:
        query = text("SELECT status FROM outbox_events WHERE aggregate_id = :agg_id")
        status_after_fail = session.execute(query, {"agg_id": aggregate_id}).scalar_one()
        assert status_after_fail == "PENDING"
    assert mock_kafka_producer.flush.call_count > 0 # It should have tried at least once

    # --- PHASE 2: Simulate Kafka Recovery ---
    # Reset mock to ALWAYS succeed
    mock_kafka_producer.flush.side_effect = None 
    mock_kafka_producer.flush.return_value = None
    # Reset call counts to assert cleanly for this phase
    mock_kafka_producer.publish_message.reset_mock()
    mock_kafka_producer.flush.reset_mock()
    
    dispatcher_recover = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)

    # ACT 2: Run the dispatcher again to process the pending event
    task_recover = asyncio.create_task(dispatcher_recover.run())
    await asyncio.sleep(2) # Allow at least one poll cycle
    dispatcher_recover.stop()
    await task_recover

    # ASSERT 2: The event is now processed
    with Session(db_engine) as session:
        query = text("SELECT status FROM outbox_events WHERE aggregate_id = :agg_id")
        status_after_success = session.execute(query, {"agg_id": aggregate_id}).scalar_one()
        assert status_after_success == "PROCESSED"
    
    # Assert that it successfully published and flushed in this phase
    mock_kafka_producer.publish_message.assert_called_once()
    mock_kafka_producer.flush.assert_called_once()