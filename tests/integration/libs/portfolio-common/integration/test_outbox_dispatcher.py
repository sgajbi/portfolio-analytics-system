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

        with pytest.raises(ValueError, match=match_str):
            await repo.create_outbox_event(
                aggregate_type="Test", aggregate_id=None, event_type="TestEvent",
                topic="test.topic", payload={}
            )
        with pytest.raises(ValueError, match=match_str):
            await repo.create_outbox_event(
                aggregate_type="Test", aggregate_id="", event_type="TestEvent",
                topic="test.topic", payload={}
            )

def test_dispatcher_processes_and_updates_pending_events(db_engine, clean_db, smart_mock_kafka_producer):
    """
    GIVEN a pending event in the outbox_events table
    WHEN the OutboxDispatcher runs
    THEN it should publish the event and update its status to PROCESSED.
    """
    # ARRANGE
    aggregate_id = f"agg-id-{uuid.uuid4()}"
    with Session(db_engine) as session:
        with session.begin():
            session.add(OutboxEvent(
                aggregate_type="TestAggregate", aggregate_id=aggregate_id, status="PENDING",
                event_type="TestEvent", payload=json.dumps({"msg": "hi"}), topic="test.topic"
            ))

    # ACT: Run one synchronous, deterministic cycle
    dispatcher = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer)
    dispatcher._process_batch_sync()

    # ASSERT
    smart_mock_kafka_producer.publish_message.assert_called_once()
    with Session(db_engine) as session:
        result = session.execute(text("SELECT status FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}).scalar_one()
        assert result == "PROCESSED"

def test_dispatcher_propagates_correlation_id(db_engine, clean_db, smart_mock_kafka_producer):
    """
    GIVEN multiple pending events, one with a correlation_id and one without
    WHEN the OutboxDispatcher runs
    THEN it should publish both with the correct correlation_id in the Kafka headers.
    """
    # ARRANGE
    agg_id_1 = f"agg-id-{uuid.uuid4()}"
    agg_id_2 = f"agg-id-{uuid.uuid4()}"
    existing_corr_id = f"corr-id-{uuid.uuid4()}"

    with Session(db_engine) as session:
        with session.begin():
            # Event with an existing correlation ID
            session.add(OutboxEvent(
                aggregate_type="TestCorrId", aggregate_id=agg_id_1, status="PENDING",
                event_type="EventWithCorrId", payload='{}', topic="test.topic",
                correlation_id=existing_corr_id
            ))
            # Event without a correlation ID
            session.add(OutboxEvent(
                aggregate_type="TestCorrId", aggregate_id=agg_id_2, status="PENDING",
                event_type="EventWithoutCorrId", payload='{}', topic="test.topic",
                correlation_id=None
            ))

    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer)
    dispatcher._process_batch_sync()

    # ASSERT
    assert smart_mock_kafka_producer.publish_message.call_count == 2
    
    # Check call for the event that HAD a correlation ID
    call_with_id = next(c for c in smart_mock_kafka_producer.publish_message.call_args_list if c.kwargs['key'] == agg_id_1)
    headers_with_id = {key: value for key, value in call_with_id.kwargs['headers']}
    assert headers_with_id['correlation_id'] == existing_corr_id.encode('utf-8')

    # Check call for the event that DID NOT have a correlation ID
    call_without_id = next(c for c in smart_mock_kafka_producer.publish_message.call_args_list if c.kwargs['key'] == agg_id_2)
    headers_without_id = {key: value for key, value in call_without_id.kwargs['headers']}
    # It should not have a correlation_id header
    assert 'correlation_id' not in headers_without_id

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
                aggregate_type="TestResilience", aggregate_id=aggregate_id, status="PENDING",
                event_type="TestEvent", payload='{}', topic="resilience.topic"
            ))

    # FIX: Create a stateful side effect function for the mock
    original_flush_implementation = smart_mock_kafka_producer.flush.side_effect
    call_count = 0
    def stateful_flush_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("Kafka is down!")
        else:
            return original_flush_implementation(*args, **kwargs)

    smart_mock_kafka_producer.flush.side_effect = stateful_flush_side_effect
    
    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer)
    
    # 1. First poll cycle fails internally, but dispatcher should handle it
    dispatcher._process_batch_sync()

    with Session(db_engine) as session:
        status, retry_count = session.execute(text("SELECT status, retry_count FROM outbox_events WHERE aggregate_id = :id"), {"id": aggregate_id}).one()
        assert status == "PENDING"
        assert retry_count == 1

    # 2. Second poll cycle should succeed
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
                    aggregate_type="ConcurrentTest", aggregate_id=f"concurrent-agg-{i}", status="PENDING",
                    event_type="TestEvent", payload="{}", topic="concurrent.topic"
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
                    aggregate_type="BatchTest", aggregate_id=f"batch-agg-{i}", status="PENDING",
                    event_type="TestEvent", payload='{}', topic="batch.topic"
                ))

    # ACT
    dispatcher = OutboxDispatcher(kafka_producer=smart_mock_kafka_producer, batch_size=batch_size)
    dispatcher._process_batch_sync()

    # ASSERT
    assert smart_mock_kafka_producer.publish_message.call_count == batch_size
    with Session(db_engine) as session:
        processed_count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PROCESSED'")).scalar_one()
        pending_count = session.execute(text("SELECT count(*) FROM outbox_events WHERE status = 'PENDING'")).scalar_one()
        assert processed_count == batch_size
        assert pending_count == num_events - batch_size