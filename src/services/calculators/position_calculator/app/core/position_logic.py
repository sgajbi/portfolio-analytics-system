# src/services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction, PositionState
from ..core.position_models import PositionState as PositionStateDTO
from portfolio_common.events import TransactionEvent
from ..repositories.position_repository import PositionRepository
from portfolio_common.position_state_repository import PositionStateRepository
from portfolio_common.outbox_repository import OutboxRepository
from portfolio_common.config import KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC
from portfolio_common.reprocessing import EpochFencer

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Handles position recalculation. Detects back-dated transactions and triggers
    a full reprocessing by incrementing the key's epoch and re-emitting all
    historical events for that key via the outbox pattern for atomicity.
    """

    @classmethod
    async def calculate(
        cls,
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: PositionRepository,
        position_state_repo: PositionStateRepository,
        outbox_repo: OutboxRepository,
    ) -> None:
        """
        Orchestrates recalculation and reprocessing triggers for a single transaction event.
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date.date()

        fencer = EpochFencer(db_session, service_name="position-calculator")
        if not await fencer.check(event):
            return
        
        current_state = await position_state_repo.get_or_create_state(portfolio_id, security_id)
        
        latest_snapshot_date = await repo.get_latest_completed_snapshot_date(
            portfolio_id, security_id, current_state.epoch
        )
        effective_completed_date = max(
            current_state.watermark_date,
            latest_snapshot_date if latest_snapshot_date else date(1970, 1, 1)
        )
        
        is_backdated = transaction_date < effective_completed_date
        
        # A back-dated check is only relevant for an original event (epoch is None).
        # A replayed event will have an epoch and should bypass this.
        if is_backdated and event.epoch is None:
            logger.warning(
                "Back-dated transaction detected. Triggering atomic reprocessing flow via outbox.",
                extra={
                    "portfolio_id": portfolio_id, "security_id": security_id,
                    "transaction_date": transaction_date.isoformat(),
                    "effective_completed_date": effective_completed_date.isoformat(),
                    "watermark_date": current_state.watermark_date.isoformat(),
                    "current_epoch": current_state.epoch
                }
            )
            new_watermark = transaction_date - timedelta(days=1)
            
            new_state = await position_state_repo.increment_epoch_and_reset_watermark(
                portfolio_id, security_id, new_watermark
            )
            
            all_transactions = await repo.get_all_transactions_for_security(portfolio_id, security_id)
            
            logger.info(f"Atomically queuing {len(all_transactions)} events for reprocessing replay in Epoch {new_state.epoch}")
            for txn in all_transactions:
                event_to_publish = TransactionEvent.model_validate(txn)
                event_to_publish.epoch = new_state.epoch
                await outbox_repo.create_outbox_event(
                    aggregate_type='ReprocessTransaction',
                    aggregate_id=str(txn.portfolio_id),
                    event_type='ReprocessTransactionReplay',
                    topic=KAFKA_PROCESSED_TRANSACTIONS_COMPLETED_TOPIC,
                    payload=event_to_publish.model_dump(mode='json')
                )
            return

        message_epoch = event.epoch if event.epoch is not None else current_state.epoch
        await repo.delete_positions_from(portfolio_id, security_id, transaction_date, message_epoch)
        anchor_position = await repo.get_last_position_before(portfolio_id, security_id, transaction_date, message_epoch)
        transactions_to_replay = await repo.get_transactions_on_or_after(portfolio_id, security_id, transaction_date)
        
        events_to_replay = [TransactionEvent.model_validate(t) for t in transactions_to_replay]
        new_positions = cls._calculate_new_positions(anchor_position, events_to_replay, message_epoch)

        if new_positions:
            await repo.save_positions(new_positions)
        
        logger.info(f"[Calculate] Staged {len(new_positions)} position records for Epoch {message_epoch}")

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
                epoch=epoch
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
        
        if txn_type == "BUY":
            quantity += transaction.quantity
            if transaction.net_cost is not None:
                cost_basis += transaction.net_cost
            if transaction.net_cost_local is not None:
                cost_basis_local += transaction.net_cost_local
        
        elif txn_type in ["SELL", "TRANSFER_OUT"]:
            quantity -= transaction.quantity
            
            # transaction.net_cost is negative for a SELL/TRANSFER_OUT, representing the COGS.
            # Adding this negative value correctly reduces the total cost basis.
            if transaction.net_cost is not None:
                cost_basis += transaction.net_cost
            if transaction.net_cost_local is not None:
                cost_basis_local += transaction.net_cost_local

        elif txn_type == "DEPOSIT":
            quantity += transaction.gross_transaction_amount
            cost_basis += transaction.gross_transaction_amount
            cost_basis_local += transaction.gross_transaction_amount

        elif txn_type == "TRANSFER_IN": 
            quantity += transaction.quantity
            cost_basis += transaction.gross_transaction_amount 
            cost_basis_local += transaction.gross_transaction_amount
        
        elif txn_type in ["FEE", "TAX", "WITHDRAWAL"]: 
            quantity -= transaction.gross_transaction_amount
            cost_basis -= transaction.gross_transaction_amount
            cost_basis_local -= transaction.gross_transaction_amount
        
        else:
            logger.debug(f"[CalculateNext] Txn type {txn_type} does not affect position quantity/cost.")

        if quantity.is_zero():
            cost_basis = Decimal(0)
            cost_basis_local = Decimal(0)

        return PositionStateDTO(quantity=quantity, cost_basis=cost_basis, cost_basis_local=cost_basis_local)