# src/services/calculators/position_valuation_calculator/app/consumers/position_history_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from decimal import Decimal
from sqlalchemy.exc import DBAPIError

from confluent_kafka import Message
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type
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

class PositionHistoryNotFoundError(Exception):
    """Custom exception to signal a retryable race condition."""
    pass

class PositionHistoryConsumer(BaseConsumer):
    """
    Consumes position history events, values them in local and base currencies,
    and saves the result as a daily position snapshot.
    """
    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, PositionHistoryNotFoundError)),
        reraise=True
    )
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
                    outbox_repo = OutboxRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    repo = ValuationRepository(db)
                    position = await db.get(PositionHistory, position_event.id)
                    
                    if not position:
                        raise PositionHistoryNotFoundError(f"PositionHistory record with id {position_event.id} not found, likely due to replication lag. Retrying...")

                    if position.cost_basis is None or position.cost_basis_local is None:
                        logger.warning(f"PositionHistory id {position_event.id} is missing cost basis. Skipping.")
                        await idempotency_repo.mark_event_processed(event_id, position_event.portfolio_id, SERVICE_NAME, correlation_id)
                        return

                    instrument = await repo.get_instrument(position.security_id)
                    portfolio = await repo.get_portfolio(position.portfolio_id)

                    if not instrument or not portfolio:
                        logger.error(f"Instrument or Portfolio not found for position {position.id}. Skipping.")
                        await idempotency_repo.mark_event_processed(event_id, position.portfolio_id, SERVICE_NAME, correlation_id)
                        return
                    
                    price = await repo.get_latest_price_for_position(position.security_id, position.position_date)
                    
                    snapshot_args = {
                        "market_price": None, "market_value": None, "market_value_local": None,
                        "unrealized_gain_loss": None, "unrealized_gain_loss_local": None,
                        "valuation_status": 'UNVALUED'
                    }

                    if price:
                        snapshot_args["market_price"] = price.price
                        price_to_instrument_fx = await repo.get_fx_rate(price.currency, instrument.currency, position.position_date)
                        instrument_to_portfolio_fx = await repo.get_fx_rate(instrument.currency, portfolio.base_currency, position.position_date)

                        valuation_result = ValuationLogic.calculate_valuation(
                            quantity=position.quantity,
                            market_price=price.price,
                            cost_basis_base=position.cost_basis,
                            cost_basis_local=position.cost_basis_local,
                            price_currency=price.currency,
                            instrument_currency=instrument.currency,
                            portfolio_currency=portfolio.base_currency,
                            price_to_instrument_fx_rate=price_to_instrument_fx.rate if price_to_instrument_fx else None,
                            instrument_to_portfolio_fx_rate=instrument_to_portfolio_fx.rate if instrument_to_portfolio_fx else None
                        )

                        if valuation_result:
                            mv_base, mv_local, pnl_base, pnl_local = valuation_result
                            snapshot_args.update({
                                "market_value": mv_base, "market_value_local": mv_local,
                                "unrealized_gain_loss": pnl_base, "unrealized_gain_loss_local": pnl_local,
                                "valuation_status": 'VALUED'
                            })

                    snapshot_to_save = DailyPositionSnapshot(
                        portfolio_id=position.portfolio_id, security_id=position.security_id,
                        date=position.position_date, quantity=position.quantity,
                        cost_basis=position.cost_basis, cost_basis_local=position.cost_basis_local,
                        **snapshot_args
                    )
                    
                    persisted_snapshot = await repo.upsert_daily_snapshot(snapshot_to_save)
                    completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)
                    
                    await outbox_repo.create_outbox_event(
                        aggregate_type='DailyPositionSnapshot',
                        aggregate_id=persisted_snapshot.portfolio_id,
                        event_type='DailyPositionSnapshotPersisted',
                        topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                        payload=completion_event.model_dump(mode='json'),
                        correlation_id=correlation_id
                    )
                    await idempotency_repo.mark_event_processed(event_id, position.portfolio_id, SERVICE_NAME, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, PositionHistoryNotFoundError):
            logger.warning(f"Database API or race condition error for event {event_id}. Retrying...", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)