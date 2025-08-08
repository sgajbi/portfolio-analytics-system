# services/calculators/position-valuation-calculator/app/consumers/position_history_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from decimal import Decimal

from confluent_kafka import Message
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PositionHistoryPersistedEvent, DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import DailyPositionSnapshot, PositionHistory
from portfolio_common.config import KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.logging_utils import correlation_id_var
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator-from-position"

class PositionHistoryConsumer(BaseConsumer):
    """
    Consumes position history events, values them in the instrument's currency,
    and saves the result as a daily position snapshot.
    """
    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()

        try:
            event_data = json.loads(value)
            position_event = PositionHistoryPersistedEvent.model_validate(event_data)

            logger.info(f"Valuing transaction-based position for id {position_event.id}", extra={"event_id": event_id})

            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository()

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    repo = ValuationRepository(db)

                    position = await db.get(PositionHistory, position_event.id)
                    if not position:
                        logger.warning(f"PositionHistory with id {position_event.id} not found. Marking as processed to skip.")
                        await idempotency_repo.mark_event_processed(event_id, position_event.portfolio_id, SERVICE_NAME, correlation_id)
                        return

                    instrument = await repo.get_instrument(position.security_id)
                    if not instrument:
                        logger.error(f"Instrument '{position.security_id}' not found. Cannot value position. Skipping.")
                        await idempotency_repo.mark_event_processed(event_id, position.portfolio_id, SERVICE_NAME, correlation_id)
                        return

                    price = await repo.get_latest_price_for_position(
                        security_id=position.security_id,
                        position_date=position.position_date
                    )
                    
                    market_value = None
                    market_price = None
                    valuation_status = 'UNVALUED'

                    if price:
                        market_price = price.price
                        fx_rate_value = None
                        if price.currency != instrument.currency:
                            fx_rate = await repo.get_fx_rate(price.currency, instrument.currency, position.position_date)
                            if fx_rate:
                                fx_rate_value = fx_rate.rate
                        
                        market_value = ValuationLogic.calculate_market_value(
                            quantity=position.quantity,
                            market_price=market_price,
                            price_currency=price.currency,
                            instrument_currency=instrument.currency,
                            fx_rate=fx_rate_value
                        )

                    if market_value is not None:
                        valuation_status = 'VALUED'
                    else:
                        reason = "market price" if price is None else "FX rate to align price currency"
                        logger.warning(f"Missing {reason} for {position.security_id} on or before {position.position_date}. Creating un-valued snapshot.")
                        market_price = None # Clear price if valuation failed

                    snapshot_to_save = DailyPositionSnapshot(
                        portfolio_id=position.portfolio_id,
                        security_id=position.security_id,
                        date=position.position_date,
                        quantity=position.quantity,
                        cost_basis=position.cost_basis,
                        market_price=market_price,
                        market_value=market_value,
                        unrealized_gain_loss=None, # Set to None as cost_basis currency is ambiguous
                        valuation_status=valuation_status
                    )

                    persisted_snapshot = await repo.upsert_daily_snapshot(snapshot_to_save)

                    completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)
                    outbox_repo.create_outbox_event(
                        db_session=db,
                        aggregate_type='DailyPositionSnapshot',
                        aggregate_id=str(persisted_snapshot.id),
                        event_type='DailyPositionSnapshotPersisted',
                        topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                        payload=completion_event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )

                    await idempotency_repo.mark_event_processed(event_id, position.portfolio_id, SERVICE_NAME, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)