# services/calculators/cost_calculator_service/app/consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import DBAPIError, IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC

from financial_calculator_engine.engine.transaction_processor import TransactionProcessor  # absolute import
from .repository import CostCalculatorRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cost-calculator"

class CostCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction events, calculates costs/realized P&L,
    persists updates, and emits a *full TransactionEvent* payload downstream.
    """
    def _get_transaction_processor(self) -> TransactionProcessor:
        return TransactionProcessor()

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
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
                    repo = CostCalculatorRepository(db)
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository()

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning("Event already processed. Skipping.")
                        await tx.rollback()
                        return

                    # Pull prior history, base currency, and fx rate needed by the engine
                    history = await repo.get_transaction_history(
                        portfolio_id=event.portfolio_id,
                        security_id=event.security_id
                    )
                    portfolio = await repo.get_portfolio(event.portfolio_id)
                    fx_rate = await repo.get_fx_rate(
                        event.trade_currency, portfolio.base_currency, event.transaction_date.date()
                    )

                    processor = self._get_transaction_processor()
                    processed, _ = processor.process_transactions(
                        history, [event], portfolio.base_currency, fx_rate
                    )

                    # Persist results produced by the engine
                    for p in processed:
                        await repo.update_transaction_costs(p)

                    # Emit the *same* TransactionEvent downstream so consumers can revalidate/rehydrate as needed
                    outbox_repo.create_outbox_event(
                        db_session=db,
                        aggregate_type='ProcessedTransaction',
                        aggregate_id=event.transaction_id,
                        event_type='ProcessedTransactionPersisted',
                        topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                        payload=event.model_dump(mode='json'),
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
            logger.error("Invalid TransactionEvent; sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError):
            logger.warning("DB error; will retry...", exc_info=False)
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error processing transaction {getattr(event,'transaction_id','UNKNOWN')}. Sending to DLQ.",
                exc_info=True
            )
            await self._send_to_dlq_async(msg, e)
