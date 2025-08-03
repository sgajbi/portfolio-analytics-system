# libs/portfolio-common/tests/integration/test_outbox_dispatcher.py
import pytest
import asyncio
import json
import uuid
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from sqlalchemy import text

from portfolio_common.database_models import OutboxEvent
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.outbox_dispatcher import OutboxDispatcher

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock of the KafkaProducer for testing."""
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    mock.flush = MagicMock()
    return mock

async def test_dispatcher_processes_and_updates_pending_events(db_engine, clean_db, mock_kafka_producer):
    """
    GIVEN a pending event in the outbox_events table
    WHEN the OutboxDispatcher runs
    THEN it should publish the event to Kafka and update its status to PROCESSED.
    """
    correlation_id = f"corr-id-{uuid.uuid4()}"
    aggregate_id = f"agg-id-{uuid.uuid4()}"
    event_payload = {"message": "hello world"}

    with Session(db_engine) as session:
        with session.begin():
            session.add(OutboxEvent(
                aggregate_type="TestAggregate",
                aggregate_id=aggregate_id,
                event_type="TestEvent",
                payload=json.dumps(event_payload),
                topic="test.topic",
                status="PENDING",
                correlation_id=correlation_id
            ))

    dispatcher = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)
    dispatcher_task = asyncio.create_task(dispatcher.run())
    await asyncio.sleep(2)
    dispatcher.stop()
    await dispatcher_task

    mock_kafka_producer.publish_message.assert_called_once()
    with Session(db_engine) as session:
        result = session.execute(
            text("SELECT status FROM outbox_events WHERE aggregate_id = :agg_id"),
            {"agg_id": aggregate_id}
        ).scalar_one()
        assert result == "PROCESSED"

async def test_dispatcher_handles_kafka_publish_failure(db_engine, clean_db, mock_kafka_producer):
    """
    GIVEN a pending event and a failing Kafka producer
    WHEN the dispatcher runs
    THEN it should retry multiple times and eventually succeed.
    """
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

    # Simulate Kafka being down for 2 attempts, then recovering
    mock_kafka_producer.flush.side_effect = [
        Exception("Kafka is down! Attempt 1"),
        Exception("Kafka is down! Attempt 2"),
        None # Success on the 3rd attempt
    ]
    
    dispatcher = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=10)

    # ACT: Run the dispatcher. Tenacity will handle the retries internally.
    task = asyncio.create_task(dispatcher.run())
    # Wait long enough for the initial attempt + tenacity's exponential backoff retries
    await asyncio.sleep(8) # <-- INCREASED WAIT TIME
    dispatcher.stop()
    await task

    # ASSERT
    # 1. Verify flush was called 3 times (2 failures, 1 success)
    assert mock_kafka_producer.flush.call_count == 3

    # 2. Verify the event is now processed
    with Session(db_engine) as session:
        status_after_success = session.execute(
            text("SELECT status FROM outbox_events WHERE aggregate_id = :agg_id"),
            {"agg_id": aggregate_id}
        ).scalar_one()
        assert status_after_success == "PROCESSED"

async def test_dispatcher_is_concurrent_safe(db_engine, clean_db, mock_kafka_producer):
    """
    GIVEN multiple pending events in the outbox
    WHEN two dispatchers run concurrently
    THEN each event should be processed exactly once.
    """
    num_events = 10
    events = []
    for i in range(num_events):
        events.append(OutboxEvent(
            aggregate_type="ConcurrentTest",
            aggregate_id=f"concurrent-agg-{i}",
            event_type="TestEvent",
            payload=json.dumps({"index": i}),
            topic="concurrent.topic",
            status="PENDING"
        ))

    with Session(db_engine) as session:
        with session.begin():
            session.add_all(events)

    dispatcher1 = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=0.5)
    dispatcher2 = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=0.5)

    task1 = asyncio.create_task(dispatcher1.run())
    task2 = asyncio.create_task(dispatcher2.run())
    await asyncio.sleep(3)
    dispatcher1.stop()
    dispatcher2.stop()
    await asyncio.gather(task1, task2)

    assert mock_kafka_producer.publish_message.call_count == num_events
    with Session(db_engine) as session:
        count = session.execute(
            text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")
        ).scalar_one()
        assert count == num_events

async def test_dispatcher_respects_batch_size(db_engine, clean_db, mock_kafka_producer):
    """
    GIVEN more events than the batch size
    WHEN the dispatcher runs for one cycle
    THEN it should only process a single batch of events.
    """
    # ARRANGE
    num_events = 15
    batch_size = 10
    events = [OutboxEvent(
        aggregate_type="BatchTest",
        aggregate_id=f"batch-agg-{i}",
        event_type="TestEvent",
        payload=json.dumps({"index": i}),
        topic="batch.topic",
        status="PENDING"
    ) for i in range(num_events)]

    with Session(db_engine) as session:
        with session.begin():
            session.add_all(events)

    # ACT
    dispatcher = OutboxDispatcher(
        kafka_producer=mock_kafka_producer,
        batch_size=batch_size
    )
    # Directly call the synchronous processing method once for deterministic testing
    dispatcher._process_batch_sync()

    # ASSERT
    assert mock_kafka_producer.publish_message.call_count == batch_size
    with Session(db_engine) as session:
        processed_count = session.execute(
            text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")
        ).scalar_one()
        pending_count = session.execute(
            text("SELECT count(*) FROM outbox_events WHERE status = 'PENDING'")
        ).scalar_one()
        assert processed_count == batch_size
        assert pending_count == num_events - batch_size