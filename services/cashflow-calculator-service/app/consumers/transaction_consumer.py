import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.events import TransactionEvent, CashflowCalculatedEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_CASHFLOW_CALCULATED_TOPIC

from ..core.cashflow_config import get_rule_for_transaction
from ..core.cashflow_logic import CashflowLogic
from ..repositories.cashflow_repository import CashflowRepository

logger = logging.getLogger(__name__)

class CashflowCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction completion events, calculates the corresponding
    cashflow, persists it, and publishes a completion event.
    """

    async def process_message(self, msg: Message):
        """
        Processes a single transaction message from Kafka.
        """
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')

        try:
            # 1. Validate the incoming message
            event_data = json.loads(value)
            transaction_event = TransactionEvent.model_validate(event_data)

            # 2. Get the business rule for this transaction type
            rule = get_rule_for_transaction(transaction_event.transaction_type)
            if not rule:
                logger.info(
                    f"No cashflow rule found for transaction type '{transaction_event.transaction_type}'. "
                    f"Skipping cashflow calculation for txn {transaction_event.transaction_id}."
                )
                return

            # 3. Apply the logic to calculate the cashflow
            cashflow_to_save = CashflowLogic.calculate(transaction_event, rule)

            # 4. Persist to the database
            with next(get_db_session()) as db:
                repo = CashflowRepository(db)
                saved_cashflow = repo.create_cashflow(cashflow_to_save)

            # 5. Publish completion event if persistence was successful
            if saved_cashflow and self._producer:
                completion_event = CashflowCalculatedEvent.model_validate(saved_cashflow)
                self._producer.publish_message(
                    topic=KAFKA_CASHFLOW_CALCULATED_TOPIC,
                    key=completion_event.transaction_id,
                    value=completion_event.model_dump(mode='json', by_alias=True)
                )
                self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq(msg, e)
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}': {e}", exc_info=True)
            await self._send_to_dlq(msg, e)