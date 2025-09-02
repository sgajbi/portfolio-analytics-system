# services/calculators/cashflow_calculator_service/app/consumers/transaction_consumer.py
import logging
import json
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from tenacity import retry, stop_after_attempt, wait_fixed, before_log, retry_if_exception_type
from confluent_kafka import Message
from typing import Dict, Optional

from portfolio_common.kafka_consumer import BaseConsumer
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.events import TransactionEvent, CashflowCalculatedEvent
from portfolio_common.db import get_async_db_session
from portfolio_common.config import KAFKA_CASHFLOW_CALCULATED_TOPIC
from portfolio_common.idempotency_repository import IdempotencyRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.reprocessing import EpochFencer
from portfolio_common.database_models import CashflowRule

from ..core.cashflow_logic import CashflowLogic
from ..repositories.cashflow_repository import CashflowRepository
from ..repositories.cashflow_rules_repository import CashflowRulesRepository

logger = logging.getLogger(__name__)

SERVICE_NAME = "cashflow-calculator"

# Module-level cache for cashflow rules.
# This will be populated once when the first message is processed.
_cashflow_rules_cache: Optional[Dict[str, CashflowRule]] = None

class NoCashflowRuleError(ValueError):
    """Custom exception for when a rule for a transaction type is not found."""
    pass


class CashflowCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction completion events, calculates the corresponding
    cashflow based on rules from the database, persists it, and writes a
    completion event to the outbox.
    """
    async def _get_rule_for_transaction(self, db_session, transaction_type: str) -> Optional[CashflowRule]:
        """
        Retrieves the cashflow rule for a given transaction type, using a
        lazy-loaded in-memory cache.
        """
        global _cashflow_rules_cache
        if _cashflow_rules_cache is None:
            logger.info("Cashflow rules cache is not populated. Loading from database...")
            repo = CashflowRulesRepository(db_session)
            rules_list = await repo.get_all_rules()
            _cashflow_rules_cache = {rule.transaction_type: rule for rule in rules_list}
            logger.info(f"Successfully loaded and cached {len(_cashflow_rules_cache)} cashflow rules.")
        
        return _cashflow_rules_cache.get(transaction_type.upper())

    async def process_message(self, msg: Message):
        await self._process_message_with_retry(msg)

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(15),
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
                    outbox_repo = OutboxRepository(db)

                    fencer = EpochFencer(db, service_name=SERVICE_NAME)
                    if not await fencer.check(event):
                        await tx.rollback() 
                        return

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning(f"Event {event_id} already processed. Skipping.")
                        await tx.rollback()
                        return

                    rule = await self._get_rule_for_transaction(db, event.transaction_type)
                    if not rule:
                        raise NoCashflowRuleError(f"No cashflow rule found for transaction type '{event.transaction_type}'. Message will be sent to DLQ.")

                    cashflow_to_save = CashflowLogic.calculate(event, rule, epoch=event.epoch)
                    saved = await cashflow_repo.create_cashflow(cashflow_to_save)

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
                        is_position_flow=saved.is_position_flow,
                        is_portfolio_flow=saved.is_portfolio_flow,
                        calculationType=saved.calculation_type,
                        epoch=saved.epoch
                    )

                    await outbox_repo.create_outbox_event(
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
        except NoCashflowRuleError as e:
            logger.error(f"Configuration error: {e}. This is a non-retryable error. Sending to DLQ.")
            await self._send_to_dlq_async(msg, e)
        except Exception as e:
            logger.error(
                f"Unexpected error processing message with key '{key}'. Sending to DLQ.",
                exc_info=True
            )
            await self._send_to_dlq_async(msg, e)