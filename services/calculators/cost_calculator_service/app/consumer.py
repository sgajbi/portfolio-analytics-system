# services/calculators/cost_calculator_service/app/consumer.py
import json
import logging
from confluent_kafka import Consumer, Message
from pydantic import ValidationError

from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.db import get_db_session
from portfolio_common.events import TransactionEvent
from portfolio_common.kafka_utils import get_kafka_producer
from portfolio_common.idempotency_repository import IdempotencyRepository # NEW IMPORT
from src.services.transaction_processor import TransactionProcessor
from src.core.models.transaction import Transaction as EngineTransaction
from src.logic.parser import TransactionParser
from src.logic.sorter import TransactionSorter
from src.logic.disposition_engine import DispositionEngine
from src.logic.cost_calculator import CostCalculator
from src.logic.error_reporter import ErrorReporter
from src.core.enums.cost_method import CostMethod
from src.logic.cost_basis_strategies import FIFOBasisStrategy, AverageCostBasisStrategy
from src.core.config.settings import Settings
from .repository import CostCalculatorRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVICE_NAME = "cost-calculator" # NEW: Define service name

class CostCalculatorConsumer:
    def __init__(self, bootstrap_servers: str, topic: str, group_id: str):
        self.topic = topic
        self.consumer_config = {
            'bootstrap.servers': bootstrap_servers,
            'group.id': group_id,
            'auto.offset.reset': 'earliest',
            'enable.auto.commit': False,
        }
        self.consumer = Consumer(self.consumer_config)
        self.consumer.subscribe([self.topic])
        self._producer = get_kafka_producer()
        logger.info(f"Consumer subscribed to topic: {self.topic}")

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

    def start_consuming(self):
        try:
            while True:
                msg = self.consumer.poll(timeout=1.0)
                if not msg or msg.error(): continue
                try:
                    self._process_message(msg)
                    self.consumer.commit(asynchronous=False)
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
        finally:
            self.consumer.close()

    def _process_message(self, msg: Message):
        message_value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}" # NEW: Generate event ID
        logger.info(f"Received message: {message_value[:200]}", extra={"event_id": event_id})

        try:
            data = json.loads(message_value)
            new_transaction_event = TransactionEvent.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Failed to parse message into TransactionEvent model: {e}")
            return

        processor = self._get_transaction_processor()
        db_txn_to_update = None
        processed_result = None

        with next(get_db_session()) as db:
            idempotency_repo = IdempotencyRepository(db)

            # Use a single atomic transaction for the check, business logic, and update
            with db.begin():
                if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                    logger.warning(
                        f"Event {event_id} has already been processed by {SERVICE_NAME}. Skipping.",
                        extra={"event_id": event_id, "service_name": SERVICE_NAME}
                    )
                    return

                repo = CostCalculatorRepository(db)

                existing_db_txns = repo.get_transaction_history(
                    portfolio_id=new_transaction_event.portfolio_id,
                    security_id=new_transaction_event.security_id
                )

                existing_txns_raw = [EngineTransaction.model_validate(t).model_dump(by_alias=True) for t in existing_db_txns]
                new_txn_raw = [new_transaction_event.model_dump()]

                processed, errored = processor.process_transactions(
                    existing_transactions_raw=existing_txns_raw,
                    new_transactions_raw=new_txn_raw
                )

                if errored:
                    for e in errored:
                        logger.error(f"Transaction {e.transaction_id} failed processing: {e.error_reason}")
                        # Even with errors, we mark the event as processed to avoid retrying a failing message
                        idempotency_repo.mark_event_processed(event_id, new_transaction_event.portfolio_id, SERVICE_NAME)
                        return # Stop processing this message

                if processed:
                    processed_result = processed[0]
                    db_txn_to_update = repo.update_transaction_costs(processed_result)

                    if db_txn_to_update:
                        logger.info(f"Successfully calculated costs for transaction {processed_result.transaction_id}.")
                        # Mark as processed inside the transaction
                        idempotency_repo.mark_event_processed(event_id, new_transaction_event.portfolio_id, SERVICE_NAME)
                    else:
                        logger.error(f"Failed to find transaction {processed_result.transaction_id} in DB to update.")
                        # Do not mark as processed, let the transaction rollback

        # Publishing happens AFTER the database transaction has been successfully committed
        if db_txn_to_update and processed_result:
            event_data_to_publish = new_transaction_event.model_dump()
            event_data_to_publish['net_cost'] = processed_result.net_cost
            event_data_to_publish['gross_cost'] = processed_result.gross_cost
            event_data_to_publish['realized_gain_loss'] = processed_result.realized_gain_loss
            completion_event = TransactionEvent.model_validate(event_data_to_publish)

            self._producer.publish_message(
                topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                key=completion_event.portfolio_id,
                value=completion_event.model_dump(mode='json')
            )
            self._producer.flush(timeout=5)
            logger.info(f"Published processed completion event for {completion_event.transaction_id}")