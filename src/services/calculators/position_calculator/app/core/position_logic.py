# src/services/calculators/position_calculator/app/core/position_logic.py
import logging
from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import PositionHistory, Transaction as DBTransaction
from ..core.position_models import PositionState
from portfolio_common.events import TransactionEvent
from ..repositories.position_repository import PositionRepository
from portfolio_common.logging_utils import correlation_id_var

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Position Calculator:
    Responsible for recalculating positions and routing to the correct
    downstream process (Valuation or Recalculation) based on the transaction date.
    """

    @classmethod
    async def calculate(
        cls,
        event: TransactionEvent,
        db_session: AsyncSession,
        repo: PositionRepository,
        is_recalculation_event: bool = False
    ) -> List[PositionHistory]:
        """
        Orchestrates recalculation and job routing for a single transaction event.
        """
        portfolio_id = event.portfolio_id
        security_id = event.security_id
        transaction_date = event.transaction_date.date()
        correlation_id = correlation_id_var.get()

        await repo.delete_positions_from(portfolio_id, security_id, transaction_date)
        anchor_position = await repo.get_last_position_before(portfolio_id, security_id, transaction_date)
        transactions_to_replay = await repo.get_transactions_on_or_after(portfolio_id, security_id, transaction_date)
        
        events_to_replay = [TransactionEvent.model_validate(t) for t in transactions_to_replay]
        new_positions = cls._calculate_new_positions(anchor_position, events_to_replay)

        if new_positions:
            await repo.save_positions(new_positions)
            final_position_state = new_positions[-1]

            # ROUTING LOGIC: Decide which job to create
            latest_business_date = await repo.get_latest_business_date()
            is_backdated = latest_business_date and final_position_state.position_date < latest_business_date

            if is_backdated and not is_recalculation_event:
                logger.info(f"Backdated transaction {event.transaction_id} detected. Staging recalculation job.")
                await repo.create_recalculation_job(
                    portfolio_id=final_position_state.portfolio_id,
                    security_id=final_position_state.security_id,
                    from_date=final_position_state.position_date,
                    correlation_id=correlation_id
                )
            else:
                await repo.upsert_valuation_job(
                    portfolio_id=final_position_state.portfolio_id,
                    security_id=final_position_state.security_id,
                    valuation_date=final_position_state.position_date,
                    correlation_id=correlation_id
                )

        logger.info(f"[Calculate] Staged {len(new_positions)} position records for Portfolio={portfolio_id}, Security={security_id}")
        return new_positions

    @staticmethod
    def _calculate_new_positions(
        anchor_position: PositionHistory | None,
        transactions: List[TransactionEvent]
    ) -> List[PositionHistory]:
        if not transactions:
            return []

        current_state = PositionState(
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
                cost_basis_local=new_state.cost_basis_local
            )
            new_history_records.append(new_position_record)
            
            current_state = new_state
            
        return new_history_records

    @staticmethod
    def calculate_next_position(current_state: PositionState, transaction: TransactionEvent) -> PositionState:
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

        return PositionState(quantity=quantity, cost_basis=cost_basis, cost_basis_local=cost_basis_local)