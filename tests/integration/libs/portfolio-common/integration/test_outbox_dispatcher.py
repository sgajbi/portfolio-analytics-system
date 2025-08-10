# libs/portfolio-common/tests/integration/test_outbox_dispatcher.py
import pytest
import asyncio
import json
import uuid
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from sqlalchemy import text

# Import async session tools
from portfolio_common.db import AsyncSessionLocal
from portfolio_common.database_models import OutboxEvent
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.outbox_dispatcher import OutboxDispatcher
from portfolio_common.outbox_repository import OutboxRepository

@pytest.fixture
def smart_mock_kafka_producer() -> MagicMock:
    """
    Provides a more realistic mock of KafkaProducer that captures and
    executes the `on_delivery` callback to simulate successful delivery.
    """
    mock = MagicMock(spec=KafkaProducer)
    callbacks = []

    def _publish_message(**kwargs):
        # Capture the callback and its associated outbox_id
        cb = kwargs.get("on_delivery")
        outbox_id = kwargs.get("outbox_id")
        if cb and outbox_id:
            callbacks.append((outbox_id, cb))

    def _flush(timeout=10):
        # Simulate successful delivery for all captured callbacks
        for outbox_id, cb in callbacks:
            cb(outbox_id, True, None) # Simulate success
        callbacks.clear() # Clear after flushing

    mock.publish_message.side_effect = _publish_message
    mock.flush.side_effect = _flush
    return mock

@pytest.mark.asyncio
async def test_create_outbox_event_fails_with_missing_aggregate_id(db_engine, clean_db):
    """
    GIVEN an attempt to create an outbox event with a missing or empty aggregate_id
    WHEN create_outbox_event is called
    THEN it should raise a ValueError.
    """
    async with AsyncSessionLocal() as session:
        repo = OutboxRepository(session)
        
        match_str = "aggregate_id \\(portfolio_id\\) is required for outbox events"

        # Test with a None value
        with pytest.raises(ValueError, match=match_str):
            await repo.create_outbox_event(
                aggregate_type="Test",
                aggregate_id=None,
                event_type="TestEvent",
                topic="test.topic",
                payload={}
            )

        # Test with an empty string
        with pytest.raises(ValueError, match=match_str):
            await repo.create_outbox_event(
                aggregate_type="Test",
                aggregate_id="",
                event_type="TestEvent",
                topic="test.topic",
                payload={}
            )

def test_dispatcher_processes_and_updates_pending_events(db_engine, clean_db, smart_mock_kafka_producer):
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

    # ACT: Run one synchronous, deterministic cycle
    dispatcher = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer, poll_interval=1)
    dispatcher._process_batch_sync()

    # ASSERT
    smart_mock_kafka_producer.publish_message.assert_called_once()
    call_args = smart_mock_kafka_producer.publish_message.call_args.kwargs
    assert call_args['key'] == aggregate_id

    with Session(db_engine) as session:
        result = session.execute(text("SELECT status FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}).scalar_one()
        assert result == "PROCESSED"

def test_dispatcher_recovers_after_failure(db_engine, clean_db, smart_mock_kafka_producer):
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
    smart_mock_kafka_producer.flush.side_effect = [Exception("Kafka is down!"), smart_mock_kafka_producer.flush.side_effect]
    
    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer, poll_interval=1)
    
    # 1. Simulate the first poll cycle, which is expected to fail internally
    dispatcher._process_batch_sync()

    with Session(db_engine) as session:
        status, retry_count = session.execute(text("SELECT status, retry_count FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}).one()
        assert status == "PENDING"
        assert retry_count == 1

    # 2. Simulate the second poll cycle, which is expected to succeed
    dispatcher._process_batch_sync()

    # ASSERT
    assert smart_mock_kafka_producer.flush.call_count == 2

    with Session(db_engine) as session:
        status = session.execute(text("SELECT status FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}).scalar_one()
        assert status == "PROCESSED"


@pytest.mark.asyncio
async def test_dispatcher_is_concurrent_safe(db_engine, clean_db, smart_mock_kafka_producer):
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
    dispatcher1 = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer, poll_interval=0.1, batch_size=5)
    dispatcher2 = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer, poll_interval=0.1, batch_size=5)
    task1 = asyncio.create_task(dispatcher1.run())
    task2 = asyncio.create_task(dispatcher2.run())
    await asyncio.sleep(1) 
    dispatcher1.stop()
    dispatcher2.stop()
    await asyncio.gather(task1, task2)

    # ASSERT: The most important check is that all events were processed exactly once.
    with Session(db_engine) as session:
        count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")).scalar_one()
        assert count == num_events

def test_dispatcher_respects_batch_size(db_engine, clean_db, smart_mock_kafka_producer):
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
    dispatcher = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer, batch_size=batch_size)
    dispatcher._process_batch_sync() # Call once deterministically

    # ASSERT
    assert smart_mock_kafka_producer.publish_message.call_count == batch_size
    with Session(db_engine) as session:
        processed_count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")).scalar_one()
        pending_count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PENDING'")).scalar_one()
        assert processed_count == batch_size
        assert pending_count == num_events - batch_size