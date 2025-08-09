# services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py
import logging
import json
from pydantic import ValidationError
from confluent_kafka import Message
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, CashflowCalculatedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.config import KAFKA_CASHFLOW_CALCULATED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository

from ..core.cashflow_config import get_rule_for_transaction
from ..core.cashflow_logic import CashflowLogic
from ..repositories.cashflow_repository import CashflowRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cashflow-calculator"

class CashflowCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction completion events, calculates the corresponding
    cashflow, persists it, and writes a completion event to the outbox.
    """
    async def process_message(self, msg: Message):
        await self._process_message_with_retry(msg)

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        before=before_log(logger, logging.INFO)
    )
    async def _process_message_with_retry(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()

        try:
            event_data = json.loads(value)
            event = TransactionEvent.model_validate(event_data)

            async for db in get_async_db_session():
                tx = await db.begin()
                try:
                    idempotency_repo = IdempotencyRepository(db)
                    cashflow_repo = CashflowRepository(db)
                    outbox_repo = OutboxRepository()

                    # idempotency guard
                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        await tx.rollback()
                        return

                    rule = get_rule_for_transaction(event.transaction_type)
                    if not rule:
                        # No cashflow rule -> still mark as processed to be idempotent
                        await idempotency_repo.mark_event_processed(
                            event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                        )
                        await db.commit()
                        return

                    # Calculate and persist cashflow
                    cashflow_to_save = CashflowLogic.calculate(event, rule)
                    saved = await cashflow_repo.create_cashflow(cashflow_to_save)

                    # Build the event with ALL required fields
                    completion_evt = CashflowCalculatedEvent(
                        id=saved.id,
                        transaction_id=saved.transaction_id,
                        portfolio_id=saved.portfolio_id,
                        security_id=saved.security_id,
                        cashflow_date=saved.cashflow_date,
                        amount=saved.amount,
                        currency=saved.currency,
                        classification=saved.classification,
                        timing=saved.timing,
                        level=saved.level,
                        calculationType=saved.calculation_type
                    )

                    # 🔑 Keying policy: use portfolio_id for strict partition affinity
                    outbox_repo.create_outbox_event(
                        db=db,  # align with repository signature from Step 2
                        aggregate_type='Cashflow',
                        aggregate_id=str(saved.portfolio_id),
                        event_type='CashflowCalculated',
                        topic=KAFKA_CASHFLOW_CALCULATED_TOPIC,
                        payload=completion_evt.model_dump(mode='json'),
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
            logger.error("Message validation failed. Sending to DLQ.", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid cashflow event payload"))
        except IntegrityError:
            logger.warning("DB integrity error; will retry...", exc_info=False)
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error processing message with key '{key}'. Sending to DLQ.",
                exc_info=True
            )
            await self._send_to_dlq_async(msg, e)
