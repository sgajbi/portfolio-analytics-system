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
from portfolio_common.outbox_repository import OutboxRepository

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Provides a mock of the KafkaProducer for testing."""
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    mock.flush = MagicMock()
    return mock

# This test is synchronous, but runs correctly within an async-marked file.
def test_create_outbox_event_fails_with_missing_aggregate_id(db_engine, clean_db):
    """
    GIVEN an attempt to create an outbox event with a missing or empty aggregate_id
    WHEN create_outbox_event is called
    THEN it should raise a ValueError.
    """
    with Session(db_engine) as session:
        repo = OutboxRepository()
        
        # Test with a None value
        with pytest.raises(ValueError, match="aggregate_id is required for outbox events to ensure proper Kafka keying."):
            repo.create_outbox_event(
                db_session=session,
                aggregate_type="Test",
                aggregate_id=None,
                event_type="TestEvent",
                topic="test.topic",
                payload={}
            )

        # Test with an empty string
        with pytest.raises(ValueError, match="aggregate_id is required for outbox events to ensure proper Kafka keying."):
            repo.create_outbox_event(
                db_session=session,
                aggregate_type="Test",
                aggregate_id="",
                event_type="TestEvent",
                topic="test.topic",
                payload={}
            )

async def test_dispatcher_processes_and_updates_pending_events(db_engine, clean_db, mock_kafka_producer):
    """
    GIVEN a pending event in the outbox_events table
    WHEN the OutboxDispatcher runs
    THEN it should publish the event to Kafka and update its status to PROCESSED.
    """
    # ARRANGE
    aggregate_id = f"agg-id-{uuid.uuid4()}"
    event_payload = {"message": "hello world"}
    with Session(db_engine) as session:
        with session.begin():
            session.add(OutboxEvent(
                aggregate_type="TestAggregate",
                aggregate_id=aggregate_id,
                status="PENDING",
                event_type="TestEvent",
                payload=json.dumps(event_payload),
                topic="test.topic"
            ))

    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)
    task = asyncio.create_task(dispatcher.run())
    await asyncio.sleep(1.5) # Allow one poll cycle
    dispatcher.stop()
    await task

    # ASSERT
    mock_kafka_producer.publish_message.assert_called_once()
    # --- VERIFY KEYING BEHAVIOR ---
    call_args = mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args['key'] == aggregate_id

    with Session(db_engine) as session:
        result = session.execute(text("SELECT status FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}).scalar_one()
        assert result == "PROCESSED"

def test_dispatcher_recovers_after_failure(db_engine, clean_db, mock_kafka_producer):
    """
    GIVEN a pending event
    WHEN the dispatcher fails on its first poll and then recovers
    THEN the event should be processed on the subsequent poll.
    """
    # ARRANGE
    aggregate_id = f"agg-id-{uuid.uuid4()}"
    with Session(db_engine) as session:
        with session.begin():
            session.add(OutboxEvent(
                aggregate_type="TestResilience",
                aggregate_id=aggregate_id,
                status="PENDING",
                event_type="TestEvent",
                payload='{}',
                topic="resilience.topic"
            ))

    # Make the first call to flush fail, then succeed on the second call
    mock_kafka_producer.flush.side_effect = [Exception("Kafka is down!"), None]
    
    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)
    
    # 1. Simulate the first poll cycle, which is expected to fail and raise an exception
    with pytest.raises(Exception, match="Kafka is down!"):
        dispatcher._process_batch_sync()

    # 2. Simulate the second poll cycle, which is expected to succeed
    dispatcher._process_batch_sync()

    # ASSERT
    # 1. Verify flush was called twice (1 failure, 1 success)
    assert mock_kafka_producer.flush.call_count == 2

    # 2. Verify the event is now processed
    with Session(db_engine) as session:
        status = session.execute(text("SELECT status FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}).scalar_one()
        assert status == "PROCESSED"

async def test_dispatcher_is_concurrent_safe(db_engine, clean_db, mock_kafka_producer):
    # ARRANGE
    num_events = 10
    with Session(db_engine) as session:
        with session.begin():
            for i in range(num_events):
                session.add(OutboxEvent(
                    aggregate_type="ConcurrentTest",
                    aggregate_id=f"concurrent-agg-{i}",
                    status="PENDING",
                    event_type="TestEvent",
                    payload="{}",
                    topic="concurrent.topic"
                ))

    # ACT
    dispatcher1 = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=0.5)
    dispatcher2 = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=0.5)
    task1 = asyncio.create_task(dispatcher1.run())
    task2 = asyncio.create_task(dispatcher2.run())
    await asyncio.sleep(3)
    dispatcher1.stop()
    dispatcher2.stop()
    await asyncio.gather(task1, task2)

    # ASSERT
    assert mock_kafka_producer.publish_message.call_count == num_events
    with Session(db_engine) as session:
        count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")).scalar_one()
        assert count == num_events

def test_dispatcher_respects_batch_size(db_engine, clean_db, mock_kafka_producer):
    # ARRANGE
    num_events, batch_size = 15, 10
    with Session(db_engine) as session:
        with session.begin():
            for i in range(num_events):
                session.add(OutboxEvent(
                    aggregate_type="BatchTest",
                    aggregate_id=f"batch-agg-{i}",
                    status="PENDING",
                    event_type="TestEvent",
                    payload='{}',
                    topic="batch.topic"
                ))

    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=mock_kafka_producer, batch_size=batch_size)
    dispatcher._process_batch_sync() # Call once deterministically

    # ASSERT
    assert mock_kafka_producer.publish_message.call_count == batch_size
    with Session(db_engine) as session:
        processed_count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")).scalar_one()
        pending_count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PENDING'")).scalar_one()
        assert processed_count == batch_size
        assert pending_count == num_events - batch_size