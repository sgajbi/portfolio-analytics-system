# services/calculators/position_calculator/app/consumers/transaction_event_consumer.py
import logging
import json
from datetime import date, timedelta
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.valuation_job_repository import ValuationJobRepository
from portfolio_common.database_models import DailyPositionSnapshot

from ..repositories.position_repository import PositionRepository
from ..core.position_logic import PositionCalculator

logger = logging.getLogger(__name__)

SERVICE_NAME = "position-calculator"

class TransactionEventConsumer(BaseConsumer):
    """
    Consumes processed transaction events, rolls forward ALL prior open positions,
    recalculates new positions for the event security, persists all snapshots, 
    and creates valuation jobs. This service is the sole owner of DailyPositionSnapshot CREATION.
    """

    async def _roll_forward_portfolio_positions(
        self,
        portfolio_id: str,
        event_date: date,
        repo: PositionRepository,
        valuation_job_repo: ValuationJobRepository,
        correlation_id: str
    ):
        """
        Finds all open positions in the portfolio and creates roll-forward snapshots 
        for any days missed up to the day before the event.
        """
        # Find all securities that were open at the beginning of the event day
        open_securities = await repo.find_open_security_ids_as_of(portfolio_id, event_date - timedelta(days=1))

        for security_id in open_securities:
            last_snapshot_date = await repo.get_last_snapshot_date(portfolio_id, security_id)

            # We need to fill the gap between the last known date and the day *before* the event
            if last_snapshot_date and last_snapshot_date < (event_date - timedelta(days=1)):
                last_snapshot = await repo.get_snapshot(portfolio_id, security_id, last_snapshot_date)
                if not last_snapshot or last_snapshot.quantity == 0:
                    continue 

                logger.info(f"Gap detected for {security_id}. Rolling forward from {last_snapshot_date} to {event_date}.")
                current_fill_date = last_snapshot_date + timedelta(days=1)
                
                while current_fill_date < event_date:
                    rolled_snapshot = DailyPositionSnapshot(
                        portfolio_id=portfolio_id,
                        security_id=security_id,
                        date=current_fill_date,
                        quantity=last_snapshot.quantity,
                        cost_basis=last_snapshot.cost_basis,
                        cost_basis_local=last_snapshot.cost_basis_local,
                        valuation_status='UNVALUED'
                    )
                    await repo.upsert_daily_snapshot(rolled_snapshot)
                    await valuation_job_repo.upsert_job(
                        portfolio_id=portfolio_id,
                        security_id=security_id,
                        valuation_date=current_fill_date,
                        correlation_id=correlation_id
                    )
                    current_fill_date += timedelta(days=1)

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(10),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError)),
        reraise=True
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()

        try:
            data = json.loads(value)
            event = TransactionEvent.model_validate(data)

            async for db in get_async_db_session():
                tx = await db.begin()
                try:
                    idempotency_repo = IdempotencyRepository(db)
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning("Event already processed. Skipping.")
                        await tx.rollback()
                        return

                    repo = PositionRepository(db)
                    valuation_job_repo = ValuationJobRepository(db)
                    
                    await self._roll_forward_portfolio_positions(
                        portfolio_id=event.portfolio_id,
                        event_date=event.transaction_date.date(),
                        repo=repo,
                        valuation_job_repo=valuation_job_repo,
                        correlation_id=correlation_id
                    )

                    new_positions = await PositionCalculator.calculate(event, db, repo=repo)

                    for record in new_positions:
                        snapshot = DailyPositionSnapshot(
                            portfolio_id=record.portfolio_id,
                            security_id=record.security_id,
                            date=record.position_date,
                            quantity=record.quantity,
                            cost_basis=record.cost_basis,
                            cost_basis_local=record.cost_basis_local,
                            valuation_status='UNVALUED'
                        )
                        await repo.upsert_daily_snapshot(snapshot)

                        await valuation_job_repo.upsert_job(
                            portfolio_id=record.portfolio_id,
                            security_id=record.security_id,
                            valuation_date=record.position_date,
                            correlation_id=correlation_id
                        )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )
                    await db.commit()

                except Exception:
                    await tx.rollback()
                    raise

        except (json.JSONDecodeError, ValidationError):
            logger.error("Invalid processed transaction event; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error; will retry...", exc_info=False)
            raise
        except Exception as e:
            logger.error("Unexpected error in position calculator; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)