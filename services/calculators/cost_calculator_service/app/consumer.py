# services/calculators/cost_calculator_service/app/consumer.py
import json
import logging
import asyncio
from confluent_kafka import Message
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.db import get_db_session
from portfolio_common.events import TransactionEvent
from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.logging_utils import correlation_id_var

# CORRECTED IMPORTS: Import directly from the library's packages, not from 'src'
from services.transaction_processor import TransactionProcessor
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

    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """ Wrapper to call the retryable logic. """
        self._process_message_with_retry(msg, loop)

    @retry(wait=wait_fixed(2), stop=stop_after_attempt(3), before=before_log(logger, logging.INFO))
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        event = None

        try:
            data = json.loads(msg.value().decode('utf-8'))
            event = TransactionEvent.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Validation error for event {event_id}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
            return

        processor = self._get_transaction_processor()
        
        try:
            with next(get_db_session()) as db:
                idempotency_repo = IdempotencyRepository(db)
                outbox_repo = OutboxRepository()
                repo = CostCalculatorRepository(db)

                with db.begin():
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        return

                    existing_db_txns = repo.get_transaction_history(
                        portfolio_id=event.portfolio_id,
                        security_id=event.security_id,
                        exclude_id=event.transaction_id
                    )
                    
                    existing_txns_raw = [EngineTransaction.model_validate(t).model_dump(by_alias=True) for t in existing_db_txns]
                    new_txn_raw = [event.model_dump()]

                    processed, errored = processor.process_transactions(
                        existing_transactions_raw=existing_txns_raw,
                        new_transactions_raw=new_txn_raw
                    )

                    if errored:
                        for e in errored:
                            logger.error(f"Transaction {e.transaction_id} failed processing: {e.error_reason}")
                        idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                        return

                    if processed:
                        processed_result = processed[0]
                        db_txn_to_update = repo.update_transaction_costs(processed_result)

                        if not db_txn_to_update:
                            raise Exception(f"Failed to find transaction {processed_result.transaction_id} in DB to update.")

                        event.net_cost = processed_result.net_cost
                        event.gross_cost = processed_result.gross_cost
                        event.realized_gain_loss = processed_result.realized_gain_loss

                        outbox_repo.create_outbox_event(
                            db_session=db,
                            aggregate_type='Transaction',
                            aggregate_id=event.transaction_id,
                            event_type='TransactionCostCalculated',
                            topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                            payload=event.model_dump(mode='json'),
                            correlation_id=correlation_id
                        )
                        
                        idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                        logger.info(f"Successfully calculated costs for transaction {processed_result.transaction_id}.")

        except IntegrityError as e:
             logger.warning(f"Caught IntegrityError for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Will retry...")
             raise
        except Exception as e:
            logger.error(f"Unexpected error processing transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)