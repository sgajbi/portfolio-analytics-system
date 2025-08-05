# services/calculators/position-valuation-calculator/app/consumers/market_price_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import MarketPriceEvent, DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.config import KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from ..repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator-from-price"

class MarketPriceConsumer(BaseConsumer):
    """
    Consumes market price events and creates or updates daily position snapshots
    for all affected portfolios with the new valuation. This process is idempotent.
    """
    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()

        try:
            event_data = json.loads(value)
            price_event = MarketPriceEvent.model_validate(event_data)
            
            logger.info(f"Processing market price for {price_event.security_id} on {price_event.price_date}")
            
            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository()
 
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    repo = ValuationRepository(db)
                    
                    updated_snapshots = await repo.update_snapshots_for_market_price(price_event)
                    
                    if updated_snapshots:
                        logger.info(f"Staging {len(updated_snapshots)} snapshot events for price event {event_id}")
                        for snapshot in updated_snapshots:
                            completion_event = DailyPositionSnapshotPersistedEvent.model_validate(snapshot)
                            outbox_repo.create_outbox_event(
                                db_session=db,
                                aggregate_type='DailyPositionSnapshot',
                                aggregate_id=str(snapshot.id),
                                event_type='DailyPositionSnapshotPersisted',
                                topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                                payload=completion_event.model_dump(mode='json'),
                                correlation_id=correlation_id
                            )
                    
                    await idempotency_repo.mark_event_processed(event_id, "N/A", SERVICE_NAME, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)