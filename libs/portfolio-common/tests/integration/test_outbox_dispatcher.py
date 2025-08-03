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
    mock = MagicMock(spec=KafkaProducer)
    mock.publish_message = MagicMock()
    mock.flush = MagicMock()
    return mock

async def test_dispatcher_processes_and_updates_pending_events(db_engine, clean_db, mock_kafka_producer):
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

    # Phase 1: Simulate Kafka Failure
    mock_kafka_producer.flush.side_effect = Exception("Kafka is down!")
    dispatcher_fail = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)
    task_fail = asyncio.create_task(dispatcher_fail.run())
    await asyncio.sleep(2)
    dispatcher_fail.stop()
    await task_fail

    with Session(db_engine) as session:
        status_after_fail = session.execute(
            text("SELECT status FROM outbox_events WHERE aggregate_id = :agg_id"),
            {"agg_id": aggregate_id}
        ).scalar_one()
        assert status_after_fail == "PENDING"

    # Phase 2: Simulate Kafka Recovery
    mock_kafka_producer.flush.side_effect = None
    mock_kafka_producer.flush.return_value = None
    mock_kafka_producer.publish_message.reset_mock()
    mock_kafka_producer.flush.reset_mock()

    dispatcher_recover = OutboxDispatcher(kafka_producer=mock_kafka_producer, poll_interval=1)
    task_recover = asyncio.create_task(dispatcher_recover.run())
    await asyncio.sleep(2)
    dispatcher_recover.stop()
    await task_recover

    mock_kafka_producer.publish_message.assert_called_once()
    with Session(db_engine) as session:
        status_after_success = session.execute(
            text("SELECT status FROM outbox_events WHERE aggregate_id = :agg_id"),
            {"agg_id": aggregate_id}
        ).scalar_one()
        assert status_after_success == "PROCESSED"

async def test_dispatcher_is_concurrent_safe(db_engine, clean_db, mock_kafka_producer):
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