# services/calculators/position-valuation-calculator/app/consumers/market_price_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from decimal import Decimal
from sqlalchemy.exc import DBAPIError

from confluent_kafka import Message
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import MarketPriceEvent, DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.database_models import DailyPositionSnapshot
from portfolio_common.config import KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator-from-price"

class MarketPriceConsumer(BaseConsumer):
    """
    Consumes market price events and re-values all daily position snapshots
    for all affected portfolios with the new valuation, respecting all currencies.
    """
    @retry(
        wait=wait_fixed(2), stop=stop_after_attempt(3), before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type(DBAPIError), reraise=True
    )
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
                    instrument = await repo.get_instrument(price_event.security_id)
                    if not instrument:
                        logger.error(f"Instrument '{price_event.security_id}' not found for price event. Skipping.")
                        await idempotency_repo.mark_event_processed(event_id, "N/A", SERVICE_NAME, correlation_id)
                        return
                    
                    snapshots_to_update = await repo.find_snapshots_to_update(price_event.security_id, price_event.price_date)
                    if not snapshots_to_update:
                        logger.info(f"No existing positions found needing valuation for {price_event.security_id} on {price_event.price_date}.")
                        await idempotency_repo.mark_event_processed(event_id, "N/A", SERVICE_NAME, correlation_id)
                        return

                    price_to_instrument_fx = await repo.get_fx_rate(price_event.currency, instrument.currency, price_event.price_date)
                    
                    updated_snapshots_count = 0
                    for snapshot in snapshots_to_update:
                        if not snapshot.cost_basis_local: continue

                        portfolio = await repo.get_portfolio(snapshot.portfolio_id)
                        if not portfolio: continue

                        instrument_to_portfolio_fx = await repo.get_fx_rate(instrument.currency, portfolio.base_currency, price_event.price_date)
                        
                        valuation_result = ValuationLogic.calculate_valuation(
                            quantity=snapshot.quantity, market_price=price_event.price,
                            cost_basis_base=snapshot.cost_basis, cost_basis_local=snapshot.cost_basis_local,
                            price_currency=price_event.currency, instrument_currency=instrument.currency,
                            portfolio_currency=portfolio.base_currency,
                            price_to_instrument_fx_rate=price_to_instrument_fx.rate if price_to_instrument_fx else None,
                            instrument_to_portfolio_fx_rate=instrument_to_portfolio_fx.rate if instrument_to_portfolio_fx else None
                        )

                        if valuation_result:
                            mv_base, mv_local, pnl_base, pnl_local = valuation_result
                            snapshot.market_price = price_event.price
                            snapshot.market_value = mv_base
                            snapshot.market_value_local = mv_local
                            snapshot.unrealized_gain_loss = pnl_base
                            snapshot.unrealized_gain_loss_local = pnl_local
                            snapshot.valuation_status = 'VALUED'
                            updated_snapshots_count += 1
                            
                            persisted_snapshot = await repo.upsert_daily_snapshot(snapshot)

                            completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)
                            outbox_repo.create_outbox_event(
                                db_session=db, aggregate_type='DailyPositionSnapshot',
                                # --- CHANGE: Key by portfolio_id for partition affinity ---
                                aggregate_id=persisted_snapshot.portfolio_id,
                                event_type='DailyPositionSnapshotPersisted',
                                topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                                payload=completion_event.model_dump(mode='json'), correlation_id=correlation_id
                            )
                    
                    logger.info(f"Successfully valued and staged updates for {updated_snapshots_count} snapshots.")
                    await idempotency_repo.mark_event_processed(event_id, "N/A", SERVICE_NAME, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Value: '{value}'", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except DBAPIError:
            logger.warning(f"Database API error for event {event_id}. Retrying...", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq_async(msg, e)