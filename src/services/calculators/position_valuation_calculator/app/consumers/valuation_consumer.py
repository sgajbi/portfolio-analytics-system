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

class DataNotFoundError(Exception):
    """Custom exception for retryable data fetching errors."""
    pass

class ValuationConsumer(BaseConsumer):
    """
    Consumes scheduled valuation jobs, creates/updates the daily position snapshot,
    calculates market value, and saves the result.
    """
    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, OperationalError, DataNotFoundError)),
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
            
            logger.info(f"Processing valuation job for {event.security_id} in {event.portfolio_id} on {event.valuation_date} for epoch {event.epoch}")

            async for db in get_async_db_session():
                try:
                    async with db.begin():
                        idempotency_repo = IdempotencyRepository(db)
                        outbox_repo = OutboxRepository(db)
                        repo = ValuationRepository(db)

                        if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                            logger.warning(f"Event {event_id} already processed. Skipping.")
                            return

                        # 1. Get the state of the position for the valuation date and epoch
                        position_state = await repo.get_last_position_history_before_date(
                            event.portfolio_id, event.security_id, event.valuation_date, event.epoch
                        )
                        if not position_state:
                            raise DataNotFoundError(f"Position history not found for epoch {event.epoch} of {event.security_id} on or before {event.valuation_date}")

                        # 2. Fetch all necessary reference data
                        instrument = await repo.get_instrument(event.security_id)
                        portfolio = await repo.get_portfolio(event.portfolio_id)
                        price = await repo.get_latest_price_for_position(event.security_id, event.valuation_date)
                        
                        if not instrument or not portfolio:
                            error_msg = "Missing critical data. "
                            if not instrument:
                                error_msg += f"Instrument '{event.security_id}' not found. "
                            if not portfolio:
                                error_msg += f"Portfolio '{event.portfolio_id}' not found."
                            
                            logger.error(f"{error_msg} Job will be marked FAILED.")
                            await repo.update_job_status(event.portfolio_id, event.security_id, event.valuation_date, 'FAILED', failure_reason=error_msg)
                            return
                        
                        # 3. Build the initial snapshot from the position state
                        snapshot = DailyPositionSnapshot(
                            portfolio_id=event.portfolio_id,
                            security_id=event.security_id,
                            date=event.valuation_date,
                            epoch=event.epoch,
                            quantity=position_state.quantity,
                            cost_basis=position_state.cost_basis,
                            cost_basis_local=position_state.cost_basis_local
                        )

                        # 4. Perform valuation if price is available
                        if price:
                            fx_rate = await repo.get_fx_rate(instrument.currency, portfolio.base_currency, event.valuation_date)
                            if instrument.currency != portfolio.base_currency and not fx_rate:
                                snapshot.valuation_status = 'FAILED'
                                logger.error(f"Missing required FX rate for valuation. Job will be marked FAILED.")
                            else:
                                valuation_result = ValuationLogic.calculate_valuation(
                                    quantity=snapshot.quantity, market_price=price.price,
                                    cost_basis_base=snapshot.cost_basis, cost_basis_local=snapshot.cost_basis_local,
                                    price_currency=price.currency, instrument_currency=instrument.currency,
                                    portfolio_currency=portfolio.base_currency,
                                    price_to_instrument_fx_rate=None,
                                    instrument_to_portfolio_fx_rate=fx_rate.rate if fx_rate else None
                                )
                                if valuation_result:
                                    snapshot.market_price = price.price
                                    snapshot.market_value, snapshot.market_value_local, snapshot.unrealized_gain_loss, snapshot.unrealized_gain_loss_local = valuation_result
                                    snapshot.valuation_status = 'VALUED_CURRENT' if price.price_date == event.valuation_date else 'VALUED_STALE'
                                else:
                                    snapshot.valuation_status = 'FAILED'
                        else:
                            snapshot.valuation_status = 'UNVALUED'

                        # 5. Persist the snapshot and create completion event
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
                        await idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                
                except DataNotFoundError as e:
                    # This is a non-retryable, expected error if a job was created for a date before a position existed.
                    logger.warning(f"Skipping job due to missing position data: {e}", extra={"portfolio_id": event.portfolio_id, "security_id": event.security_id, "date": event.valuation_date})
                    async with db.begin():
                        repo = ValuationRepository(db)
                        idempotency_repo = IdempotencyRepository(db)
                        await repo.update_job_status(
                            event.portfolio_id, event.security_id, event.valuation_date,
                            status='SKIPPED_NO_POSITION',
                            failure_reason=str(e)
                        )
                        await idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                    # Do not re-raise, do not send to DLQ.

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}'. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
        except (DBAPIError, OperationalError, DataNotFoundError) as e:
            logger.warning(f"DB or data availability error for event {event_id}: {e}. Retrying...", exc_info=False)
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}'. Sending to DLQ.", exc_info=True)
            if event:
                async for db in get_async_db_session():
                    async with db.begin():
                        repo = ValuationRepository(db)
                        await repo.update_job_status(event.portfolio_id, event.security_id, event.valuation_date, 'FAILED', failure_reason=str(e))
            await self._send_to_dlq_async(msg, e)