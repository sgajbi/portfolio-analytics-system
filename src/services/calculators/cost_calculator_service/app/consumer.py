# src/services/calculators/cost_calculator_service/app/consumer.py
import logging
import json
from datetime import datetime
from typing import List, Any
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
from portfolio_common.database_models import Portfolio

# IMPORTANT: Import all necessary components from the engine
from engine.transaction_processor import TransactionProcessor
from logic.parser import TransactionParser
from logic.sorter import TransactionSorter
from logic.cost_basis_strategies import FIFOBasisStrategy
from logic.disposition_engine import DispositionEngine
from logic.cost_calculator import CostCalculator
from logic.error_reporter import ErrorReporter

from .repository import CostCalculatorRepository

logger = logging.getLogger(__name__)
SERVICE_NAME = "cost-calculator"

class FxRateNotFoundError(Exception):
    """Raised when a required FX rate is not yet available in the database."""
    pass

class CostCalculatorConsumer(BaseConsumer):
    """
    Consumes raw transaction events, calculates costs/realized P&L,
    persists updates, and emits a full TransactionEvent downstream.
    """
    def _get_transaction_processor(self) -> TransactionProcessor:
        """
        Correctly builds and returns an instance of the TransactionProcessor
        with all its required dependencies.
        """
        error_reporter = ErrorReporter()
        parser = TransactionParser(error_reporter=error_reporter)
        sorter = TransactionSorter()
        strategy = FIFOBasisStrategy()
        disposition_engine = DispositionEngine(cost_basis_strategy=strategy)
        cost_calculator = CostCalculator(
            disposition_engine=disposition_engine, error_reporter=error_reporter
        )
        return TransactionProcessor(
            parser=parser,
            sorter=sorter,
            disposition_engine=disposition_engine,
            cost_calculator=cost_calculator,
            error_reporter=error_reporter
        )

    def _transform_event_for_engine(self, event: TransactionEvent) -> dict:
        """
        Transforms a TransactionEvent into a raw dictionary suitable for the
        financial-calculator-engine, converting trade_fee to a Fees object structure.
        """
        event_dict = event.model_dump(mode='json')
        trade_fee = event_dict.pop('trade_fee', 0) or 0

        # The engine's calculator sums all fees in the Fees object.
        # We'll map the single fee to 'brokerage' for simplicity, as it's the most common.
        if trade_fee > 0:
            event_dict['fees'] = {'brokerage': trade_fee}
        
        return event_dict

    async def _enrich_transactions_with_fx(
        self,
        transactions: List[dict[str, Any]],
        portfolio_base_currency: str,
        repo: CostCalculatorRepository
    ) -> List[dict[str, Any]]:
        """
        Iterates through transactions, fetching and attaching FX rates for cross-currency trades.
        """
        for txn_raw in transactions:
            txn_raw['portfolio_base_currency'] = portfolio_base_currency
            
            if txn_raw.get('trade_currency') == portfolio_base_currency:
                continue

            fx_rate = await repo.get_fx_rate(
                from_currency=txn_raw['trade_currency'],
                to_currency=portfolio_base_currency,
                a_date=datetime.fromisoformat(txn_raw['transaction_date'].replace('Z', '+00:00')).date()
            )

            if not fx_rate:
                raise FxRateNotFoundError(
                    f"FX rate for {txn_raw['trade_currency']}->{portfolio_base_currency} on "
                    f"{txn_raw['transaction_date']} not found. Retrying..."
                )
            
            txn_raw['transaction_fx_rate'] = fx_rate.rate
        
        return transactions

    @retry(
        wait=wait_fixed(2),
        stop=stop_after_attempt(3),
        before=before_log(logger, logging.INFO),
        retry=retry_if_exception_type((DBAPIError, IntegrityError, FxRateNotFoundError)),
        reraise=True
    )
    async def process_message(self, msg: Message):
        key = msg.key().decode('utf-8') if msg.key() else "NoKey"
        value = msg.value().decode('utf-8')
        event_id = f"{msg.topic()}-{msg.partition()}-{msg.offset()}"
        correlation_id = correlation_id_var.get()
        event = None

        try:
            data = json.loads(value)
            event = TransactionEvent.model_validate(data)

            async for db in get_async_db_session():
                tx = await db.begin()
                try:
                    repo = CostCalculatorRepository(db)
                    idempotency_repo = IdempotencyRepository(db)
                    outbox_repo = OutboxRepository(db)

                    if await idempotency_repo.is_event_processed(event_id, SERVICE_NAME):
                        logger.warning("Event already processed. Skipping.")
                        await tx.rollback()
                        return

                    portfolio = await repo.get_portfolio(event.portfolio_id)
                    if not portfolio:
                        raise ValueError(f"Portfolio {event.portfolio_id} not found.")

                    history_db = await repo.get_transaction_history(
                        portfolio_id=event.portfolio_id,
                        security_id=event.security_id,
                        exclude_id=event.transaction_id
                    )

                    # --- FIX: Transform events to match engine's expected structure ---
                    history_raw = [self._transform_event_for_engine(TransactionEvent.model_validate(t)) for t in history_db]
                    event_raw = self._transform_event_for_engine(event)
                    
                    all_transactions_raw = await self._enrich_transactions_with_fx(
                        transactions=history_raw + [event_raw],
                        portfolio_base_currency=portfolio.base_currency,
                        repo=repo
                    )

                    new_transaction_ids = {event.transaction_id}
                    
                    processor = self._get_transaction_processor()
                    processed, errored = processor.process_transactions(
                        existing_transactions_raw=[],
                        new_transactions_raw=all_transactions_raw
                    )

                    if errored:
                        new_errors = [e for e in errored if e.transaction_id in new_transaction_ids]
                        if new_errors:
                            raise ValueError(f"Transaction engine failed: {new_errors[0].error_reason}")

                    processed_new = [p for p in processed if p.transaction_id in new_transaction_ids]

                    for p_txn in processed_new:
                        updated_txn = await repo.update_transaction_costs(p_txn)
                        full_event_to_publish = TransactionEvent.model_validate(updated_txn)

                        await outbox_repo.create_outbox_event(
                            aggregate_type='ProcessedTransaction',
                            aggregate_id=str(p_txn.portfolio_id),
                            event_type='ProcessedTransactionPersisted',
                            topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                            payload=full_event_to_publish.model_dump(mode='json'),
                            correlation_id=correlation_id
                        )

                    await idempotency_repo.mark_event_processed(
                        event_id, event.portfolio_id, SERVICE_NAME, correlation_id
                    )
                    
                    await db.commit()

                except Exception:
                    await tx.rollback()
                    raise

        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Invalid TransactionEvent; sending to DLQ. Error: {e}", exc_info=True)
            await self._send_to_dlq_async(msg, ValueError("invalid payload"))
        except (DBAPIError, IntegrityError, FxRateNotFoundError):
            logger.warning("DB or FX rate error; will retry...", exc_info=True)
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error processing transaction {getattr(event, 'transaction_id', 'UNKNOWN')}. Sending to DLQ.",
                exc_info=True
            )
            await self._send_to_dlq_async(msg, e)