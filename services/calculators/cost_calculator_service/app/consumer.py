# services/calculators/cost_calculator_service/app/consumer.py
import json
import logging
import asyncio
from confluent_kafka import Message
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, DBAPIError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type

from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.db import get_async_db_session
from portfolio_common.events import TransactionEvent
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.logging_utils import correlation_id_var

from engine.transaction_processor import TransactionProcessor
from core.models.transaction import Transaction as EngineTransaction
from logic.parser import TransactionParser
from logic.sorter import TransactionSorter
from logic.disposition_engine import DispositionEngine
from logic.cost_calculator import CostCalculator
from logic.error_reporter import ErrorReporter
from core.enums.cost_method import CostMethod
from logic.cost_basis_strategies import FIFOBasisStrategy, AverageCostBasisStrategy
from core.config.settings import Settings
from .repository import CostCalculatorRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cost-calculator"

class RequiredDataMissingError(Exception):
    """Custom exception to signal a retry due to missing dependent data."""
    pass

class CostCalculatorConsumer(BaseConsumer):
    """
    Consumes transaction events, recalculates cost basis for the full history
    of a security, persists the results, and writes a completion event to the outbox.
    """
    def _get_transaction_processor(self) -> TransactionProcessor:
        settings = Settings()
        error_reporter = ErrorReporter()
        strategy = FIFOBasisStrategy() if settings.COST_BASIS_METHOD == CostMethod.FIFO else AverageCostBasisStrategy()
        disposition_engine = DispositionEngine(cost_basis_strategy=strategy)
        cost_calculator = CostCalculator(disposition_engine, error_reporter)
        return TransactionProcessor(
            parser=TransactionParser(error_reporter),
            sorter=TransactionSorter(),
            disposition_engine=disposition_engine,
            cost_calculator=cost_calculator,
            error_reporter=error_reporter
        )

    @retry(
        wait=wait_fixed(3),
        stop=stop_after_attempt(5),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, RequiredDataMissingError)),
        reraise=True
    )
    async def process_message(self, msg: Message):
        """ Wrapper to call the retryable logic. """
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        event = None

        try:
            data = json.loads(msg.value().decode('utf-8'))
            event = TransactionEvent.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Validation error for event {event_id}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)
            return

        processor = self._get_transaction_processor()
        
        try:
            async for db in get_async_db_session():
                async with db.begin():
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository()
                    repo = CostCalculatorRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    # --- Fetch Portfolio and FX Rate ---
                    portfolio = await repo.get_portfolio(event.portfolio_id)
                    if not portfolio:
                        raise RequiredDataMissingError(f"Portfolio {event.portfolio_id} not found. Retrying...")

                    fx_rate = None
                    if event.trade_currency != portfolio.base_currency:
                        fx_rate_record = await repo.get_fx_rate(event.trade_currency, portfolio.base_currency, event.transaction_date.date())
                        if not fx_rate_record:
                            raise RequiredDataMissingError(f"FX Rate from {event.trade_currency} to {portfolio.base_currency} not found for {event.transaction_date.date()}. Retrying...")
                        fx_rate = fx_rate_record.rate
                    
                    new_txn_raw_dict = event.model_dump()
                    new_txn_raw_dict['portfolio_base_currency'] = portfolio.base_currency
                    new_txn_raw_dict['transaction_fx_rate'] = fx_rate
                    new_txn_raw = [new_txn_raw_dict]

                    existing_db_txns = await repo.get_transaction_history(
                        portfolio_id=event.portfolio_id,
                        security_id=event.security_id,
                        exclude_id=event.transaction_id
                    )
                    
                    existing_txns_raw = []
                    for t in existing_db_txns:
                        # Convert SQLAlchemy model to dict and ADD the required base currency
                        txn_dict = {c.name: getattr(t, c.name) for c in t.__table__.columns}
                        txn_dict['portfolio_base_currency'] = portfolio.base_currency
                        existing_txns_raw.append(txn_dict)

                    processed, errored = processor.process_transactions(
                        existing_transactions_raw=existing_txns_raw,
                        new_transactions_raw=new_txn_raw
                    )

                    if errored:
                        for e in errored:
                            logger.error(f"Transaction {e.transaction_id} failed processing: {e.error_reason}")
                        await idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                        return

                    if processed:
                        processed_result = processed[0]
                        db_txn_to_update = await repo.update_transaction_costs(processed_result)

                        if not db_txn_to_update:
                            raise Exception(f"Failed to find transaction {processed_result.transaction_id} in DB to update.")

                        completion_event_payload = TransactionEvent.model_validate(processed_result.model_dump())

                        outbox_repo.create_outbox_event(
                            db_session=db,
                            aggregate_type='Transaction',
                            aggregate_id=event.transaction_id,
                            event_type='TransactionCostCalculated',
                            topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                            payload=completion_event_payload.model_dump(mode='json'),
                            correlation_id=correlation_id
                        )
                        
                        await idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                        logger.info(f"Successfully calculated costs for transaction {processed_result.transaction_id}.")

        except (DBAPIError, IntegrityError, RequiredDataMissingError) as e:
             logger.warning(f"A recoverable error occurred for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}: {e}. Retrying...", exc_info=True)
             raise
        except Exception as e:
            logger.error(f"Unexpected error processing transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, e)