# services/cost-calculator-service/app/consumer.py
import json
import logging
from confluent_kafka import Consumer, KafkaException, Message
from pydantic import ValidationError

from common.config import KAFKA_BOOTSTRAP_SERVERS
from common.db import get_db_session
from common.database_models import Transaction as DBTransaction
from common.events import TransactionEvent # <-- THE FIX: Import the shared event model

# Import the TransactionProcessor from our new library
from src.services.transaction_processor import TransactionProcessor
from src.logic.parser import TransactionParser
from src.logic.sorter import TransactionSorter
from src.logic.disposition_engine import DispositionEngine
from src.logic.cost_calculator import CostCalculator
from src.logic.error_reporter import ErrorReporter
from src.core.enums.cost_method import CostMethod
from src.logic.cost_basis_strategies import FIFOBasisStrategy, AverageCostBasisStrategy
from src.core.config.settings import Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"Consumer subscribed to topic: {self.topic}")

    def _get_transaction_processor(self) -> TransactionProcessor:
        settings = Settings()
        error_reporter = ErrorReporter()
        
        if settings.COST_BASIS_METHOD == CostMethod.FIFO:
            strategy = FIFOBasisStrategy()
        else:
            strategy = AverageCostBasisStrategy()

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
                if msg is None: continue
                if msg.error():
                    logger.warning(f"Kafka consumer error: {msg.error()}. Retrying...")
                    continue
                try:
                    self._process_message(msg)
                    self.consumer.commit(asynchronous=False)
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
        finally:
            self.consumer.close()

    def _process_message(self, msg: Message):
        message_value = msg.value().decode('utf-8')
        logger.info(f"Received message: {message_value[:200]}")
        
        try:
            data = json.loads(message_value)
            # --- THE FIX: Use the correct, simple event model for validation ---
            new_transaction_event = TransactionEvent.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Failed to parse message into TransactionEvent model: {e}")
            return

        processor = self._get_transaction_processor()
        
        with next(get_db_session()) as db:
            existing_db_txns = db.query(DBTransaction).filter(
                DBTransaction.portfolio_id == new_transaction_event.portfolio_id,
                DBTransaction.instrument_id == new_transaction_event.instrument_id
            ).all()

            # The engine expects a list of dictionaries. We must convert our objects.
            # We use model_dump() which respects Pydantic aliases.
            existing_txns_raw = [TransactionEvent.model_validate(t).model_dump() for t in existing_db_txns]
            new_txn_raw = [new_transaction_event.model_dump()]

            processed, errored = processor.process_transactions(
                existing_transactions_raw=existing_txns_raw,
                new_transactions_raw=new_txn_raw
            )
            
            if errored:
                for e in errored:
                    logger.error(f"Transaction {e.transaction_id} failed processing: {e.error_reason}")

            if processed:
                result = processed[0]
                db_txn_to_update = db.query(DBTransaction).filter(
                    DBTransaction.transaction_id == result.transaction_id
                ).first()

                if db_txn_to_update:
                    logger.info(f"Updating transaction {result.transaction_id} with calculated costs.")
                    db_txn_to_update.net_cost = result.net_cost
                    db_txn_to_update.gross_cost = result.gross_cost
                    db_txn_to_update.realized_gain_loss = result.realized_gain_loss
                    db.commit()
                    logger.info(f"Successfully updated transaction {result.transaction_id}.")
                else:
                    logger.error(f"Could not find transaction {result.transaction_id} in DB to update.")