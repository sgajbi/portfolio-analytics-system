# src/services/calculators/position_valuation_calculator/app/consumers/valuation_consumer.py
import logging
import json
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError

from confluent_kafka import Message
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import PortfolioValuationRequiredEvent, DailyPositionSnapshotPersistedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.config import KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.logging_utils import correlation_id_var
from ..repositories.valuation_repository import ValuationRepository
from ..logic.valuation_logic import ValuationLogic
from portfolio_common.database_models import DailyPositionSnapshot

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-valuation-calculator"

class SnapshotNotFoundError(Exception):
    """Raised when the expected DailyPositionSnapshot is not yet in the database."""
    pass

class ValuationConsumer(BaseConsumer):
    """
    Consumes scheduled valuation jobs, calculates the market value for a position
    on a specific date, and saves the result as a daily position snapshot.
    """
    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, OperationalError, SnapshotNotFoundError)),
        reraise=True
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        event = None

        try:
            event_data = json.loads(value)
            event = PortfolioValuationRequiredEvent.model_validate(event_data)
            
            logger.info(f"Processing valuation job for {event.security_id} in {event.portfolio_id} on {event.valuation_date}")

            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository(db)
                    repo = ValuationRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    snapshot = await repo.get_daily_snapshot(event.portfolio_id, event.security_id, event.valuation_date)
                    
                    if not snapshot:
                        # --- LOGIC RESTORED: Roll forward if snapshot is missing ---
                        logger.warning(f"Snapshot for {event.valuation_date} not found. Attempting to roll forward.")
                        previous_snapshot = await repo.get_last_snapshot_before_date(event.portfolio_id, event.security_id, event.valuation_date)
                        
                        if not previous_snapshot:
                            raise SnapshotNotFoundError(f"No previous snapshot found for {event.security_id} before {event.valuation_date}. Cannot roll forward.")

                        snapshot = DailyPositionSnapshot(
                            portfolio_id=previous_snapshot.portfolio_id,
                            security_id=previous_snapshot.security_id,
                            date=event.valuation_date,
                            quantity=previous_snapshot.quantity,
                            cost_basis=previous_snapshot.cost_basis,
                            cost_basis_local=previous_snapshot.cost_basis_local
                        )
                        logger.info(f"Created new rolled-forward snapshot for {event.valuation_date} from {previous_snapshot.date}.")
                        # --- END LOGIC RESTORED ---

                    instrument = await repo.get_instrument(snapshot.security_id)
                    portfolio = await repo.get_portfolio(snapshot.portfolio_id)
                    price = await repo.get_latest_price_for_position(snapshot.security_id, snapshot.date)
                    
                    if not all([instrument, portfolio, price]):
                        logger.error(f"Missing critical data for valuation (instrument, portfolio, or price). Job will be marked FAILED. Snapshot ID: {snapshot.id if snapshot.id else 'N/A'}")
                        await repo.update_job_status(event.portfolio_id, event.security_id, event.valuation_date, 'FAILED')
                        return

                    price_to_instrument_fx = await repo.get_fx_rate(price.currency, instrument.currency, snapshot.date)
                    instrument_to_portfolio_fx = await repo.get_fx_rate(instrument.currency, portfolio.base_currency, snapshot.date)

                    valuation_result = ValuationLogic.calculate_valuation(
                        quantity=snapshot.quantity,
                        market_price=price.price,
                        cost_basis_base=snapshot.cost_basis,
                        cost_basis_local=snapshot.cost_basis_local,
                        price_currency=price.currency,
                        instrument_currency=instrument.currency,
                        portfolio_currency=portfolio.base_currency,
                        price_to_instrument_fx_rate=price_to_instrument_fx.rate if price_to_instrument_fx else None,
                        instrument_to_portfolio_fx_rate=instrument_to_portfolio_fx.rate if instrument_to_portfolio_fx else None
                    )

                    if valuation_result:
                        mv_base, mv_local, pnl_base, pnl_local = valuation_result
                        snapshot.market_price = price.price
                        snapshot.market_value = mv_base
                        snapshot.market_value_local = mv_local
                        snapshot.unrealized_gain_loss = pnl_base
                        snapshot.unrealized_gain_loss_local = pnl_local
                        snapshot.valuation_status = 'VALUED'

                        persisted_snapshot = await repo.upsert_daily_snapshot(snapshot)
                        completion_event = DailyPositionSnapshotPersistedEvent.model_validate(persisted_snapshot)
                        
                        await outbox_repo.create_outbox_event(
                            aggregate_type='DailyPositionSnapshot',
                            aggregate_id=persisted_snapshot.portfolio_id,
                            event_type='DailyPositionSnapshotPersisted',
                            topic=KAFKA_DAILY_POSITION_SNAPSHOT_PERSISTED_TOPIC,
                            payload=completion_event.model_dump(mode='json'),
                            correlation_id=correlation_id
                        )
                        await repo.update_job_status(event.portfolio_id, event.security_id, event.valuation_date, 'COMPLETE')
                    else:
                        await repo.update_job_status(event.portfolio_id, event.security_id, event.valuation_date, 'FAILED')

                    await idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}'. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, OperationalError, SnapshotNotFoundError) as e:
            logger.warning(f"Database or data availability error for event {event_id}: {e}. Retrying...", exc_info=False)
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}'. Sending to DLQ.", exc_info=True)
            if event:
                async for db in get_async_db_session():
                    async with db.begin():
                        repo = ValuationRepository(db)
                        await repo.update_job_status(event.portfolio_id, event.security_id, event.valuation_date, 'FAILED')
            await self._send_to_dlq_async(msg, e)