# services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py
import logging
import json
import asyncio
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, CashflowCalculatedEvent
from portfolio_common.db import get_db_session
from portfolio_common.config import KAFKA_CASHFLOW_CALCULATED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository

from ..core.cashflow_config import get_rule_for_transaction
from ..core.cashflow_logic import CashflowLogic
from ..repositories.cashflow_repository import CashflowRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cashflow-calculator"

class CashflowCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction completion events, calculates the corresponding
    cashflow, persists it, and publishes a completion event.
    This process is idempotent and retries on transient DB errors.
    """
    def process_message(self, msg: Message, loop: asyncio.AbstractEventLoop):
        """Wrapper to call the retryable logic."""
        self._process_message_with_retry(msg, loop)

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        before=before_log(logger, logging.INFO)
    )
    def _process_message_with_retry(self, msg: Message, loop: asyncio.AbstractEventLoop):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        saved_cashflow = None
        event = None

        try:
            event_data = json.loads(value)
            event = TransactionEvent.model_validate(event_data)

            with next(get_db_session()) as db:
                idempotency_repo = IdempotencyRepository(db)
                cashflow_repo = CashflowRepository(db)

                with db.begin():
                    if idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(
                            f"Event {event_id} has already been processed by {SERVICE_NAME}. Skipping.",
                            extra={"event_id": event_id, "service_name": SERVICE_NAME}
                        )
                        return

                    rule = get_rule_for_transaction(event.transaction_type)
                    if not rule:
                        logger.info(
                            f"No cashflow rule for type '{event.transaction_type}'. Skipping.",
                            extra={"transaction_id": event.transaction_id}
                        )
                        idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)
                        return

                    cashflow_to_save = CashflowLogic.calculate(event, rule)
                    saved_cashflow = cashflow_repo.create_cashflow(cashflow_to_save)
                    idempotency_repo.mark_event_processed(event_id, event.portfolio_id, SERVICE_NAME, correlation_id)

            if saved_cashflow and self._producer:
                completion_event = CashflowCalculatedEvent.model_validate(saved_cashflow)
                headers = [('correlation_id', correlation_id.encode('utf-8'))] if correlation_id else None
                
                self._producer.publish_message(
                    topic=KAFKA_CASHFLOW_CALCULATED_TOPIC,
                    key=completion_event.transaction_id,
                    value=completion_event.model_dump(mode='json', by_alias=True),
                    headers=headers
                )
                self._producer.flush(timeout=5)

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Message validation failed for key '{key}': {e}. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)
        except IntegrityError as e:
            logger.warning(f"Caught IntegrityError for transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Will retry...")
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing message with key '{key}'. Sending to DLQ.", exc_info=True)
            self._send_to_dlq_sync(msg, e, loop)