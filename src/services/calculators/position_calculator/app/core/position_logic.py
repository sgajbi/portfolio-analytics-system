# src/services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction, PositionState
from ..core.position_models import PositionState as PositionStateDTO
from portfolio_common.events import TransactionEvent
from ..repositories.position_repository import PositionRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.logging_utils import correlation_id_var
from portfolio_common.kafka_utils import KafkaProducer
from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Handles position recalculation. Detects back-dated transactions and triggers
    a full reprocessing by incrementing the key's epoch and re-emitting all
    historical events for that key.
    """

    @classmethod
    async def calculate(
        cls,
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: PositionRepository,
        position_state_repo: PositionStateRepository,
        kafka_producer: KafkaProducer,
        current_state: PositionState
    ) -> None:
        """
        Orchestrates recalculation and reprocessing triggers for a single transaction event.
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date.date()

        is_backdated = transaction_date <= current_state.watermark_date

        if is_backdated:
            logger.warning(
                "Back-dated transaction detected. Triggering reprocessing flow.",
                extra={
                    "portfolio_id": portfolio_id, "security_id": security_id,
                    "transaction_date": transaction_date.isoformat(),
                    "watermark_date": current_state.watermark_date.isoformat(),
                    "current_epoch": current_state.epoch
                }
            )
            new_watermark = transaction_date - timedelta(days=1)
            new_state = await position_state_repo.increment_epoch_and_reset_watermark(
                portfolio_id, security_id, new_watermark
            )
            
            all_transactions = await repo.get_all_transactions_for_security(portfolio_id, security_id)
            
            logger.info(f"Re-emitting {len(all_transactions)} transactions for Epoch {new_state.epoch}")
            for txn in all_transactions:
                event_to_publish = TransactionEvent.model_validate(txn)
                headers = [('reprocess_epoch', str(new_state.epoch).encode('utf-8'))]
                kafka_producer.publish_message(
                    topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                    key=txn.portfolio_id,
                    value=event_to_publish.model_dump(mode='json'),
                    headers=headers
                )
            kafka_producer.flush()
            return

        # --- Normal (Non-Backdated) Flow ---
        await repo.delete_positions_from(portfolio_id, security_id, transaction_date)
        anchor_position = await repo.get_last_position_before(portfolio_id, security_id, transaction_date)
        transactions_to_replay = await repo.get_transactions_on_or_after(portfolio_id, security_id, transaction_date)
        
        events_to_replay = [TransactionEvent.model_validate(t) for t in transactions_to_replay]
        new_positions = cls._calculate_new_positions(anchor_position, events_to_replay, current_state.epoch)

        if new_positions:
            await repo.save_positions(new_positions)
        
        logger.info(f"[Calculate] Staged {len(new_positions)} position records for Epoch {current_state.epoch}")

    @staticmethod
    def _calculate_new_positions(
        anchor_position: PositionHistory | None,
        transactions: List[TransactionEvent],
        epoch: int
    ) -> List[PositionHistory]:
        if not transactions:
            return []

        current_state = PositionStateDTO(
            quantity=anchor_position.quantity if anchor_position else Decimal(0),
            cost_basis=anchor_position.cost_basis if anchor_position else Decimal(0),
            cost_basis_local=anchor_position.cost_basis_local if anchor_position and anchor_position.cost_basis_local is not None else Decimal(0)
        )
        
        new_history_records = []
        
        for transaction in transactions:
            new_state = PositionCalculator.calculate_next_position(current_state, transaction)
            
            new_position_record = PositionHistory(
                portfolio_id=transaction.portfolio_id,
                security_id=transaction.security_id,
                transaction_id=transaction.transaction_id,
                position_date=transaction.transaction_date.date(),
                quantity=new_state.quantity,
                cost_basis=new_state.cost_basis,
                cost_basis_local=new_state.cost_basis_local,
                epoch=epoch # Tag record with the current epoch
            )
            new_history_records.append(new_position_record)
            
            current_state = new_state
            
        return new_history_records

    @staticmethod
    def calculate_next_position(current_state: PositionStateDTO, transaction: TransactionEvent) -> PositionStateDTO:
        quantity = current_state.quantity
        cost_basis = current_state.cost_basis
        cost_basis_local = current_state.cost_basis_local
        txn_type = transaction.transaction_type.upper()
        net_cost = transaction.net_cost if transaction.net_cost is not None else Decimal(0)
        net_cost_local = transaction.net_cost_local if transaction.net_cost_local is not None else Decimal(0)

        if txn_type == "BUY":
            quantity += transaction.quantity
            cost_basis += net_cost
            cost_basis_local += net_cost_local
        elif txn_type in ["DEPOSIT", "TRANSFER_IN"]:
            quantity += transaction.gross_transaction_amount
            cost_basis += transaction.gross_transaction_amount
            cost_basis_local += transaction.gross_transaction_amount
        elif txn_type == "SELL":
            if quantity != Decimal(0):
                proportion_sold = transaction.quantity / quantity
                cogs_base = cost_basis * proportion_sold
                cogs_local = cost_basis_local * proportion_sold
                cost_basis -= cogs_base
                cost_basis_local -= cogs_local
            quantity -= transaction.quantity
        elif txn_type in ["FEE", "TAX", "TRANSFER_OUT", "WITHDRAWAL"]:
            quantity -= transaction.gross_transaction_amount
            cost_basis -= transaction.gross_transaction_amount
            cost_basis_local -= transaction.gross_transaction_amount
        else:
            logger.debug(f"[CalculateNext] Txn type {txn_type} does not affect position quantity/cost.")

        if quantity.is_zero():
            cost_basis = Decimal(0)
            cost_basis_local = Decimal(0)

        return PositionStateDTO(quantity=quantity, cost_basis=cost_basis, cost_basis_local=cost_basis_local)