# services/calculators/cost_calculator_service/app/repository.py
from typing import List, Optional
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from decimal import Decimal
from portfolio_common.database_models import (
    Transaction as DBTransaction,
    Portfolio,
    FxRate,
    PositionLotState,
    AccruedIncomeOffsetState,
)
from core.models.transaction import Transaction as EngineTransaction

class CostCalculatorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches a portfolio by its portfolio_id string."""
        stmt = select(Portfolio).where(Portfolio.portfolio_id == portfolio_id)
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_fx_rate(self, from_currency: str, to_currency: str, a_date: date) -> Optional[FxRate]:
        """Fetches the latest FX rate on or before a given date."""
        stmt = select(FxRate).filter(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date <= a_date
        ).order_by(FxRate.rate_date.desc())
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def get_transaction_history(
        self,
        portfolio_id: str,
        security_id: str,
        exclude_id: Optional[str] = None
    ) -> List[DBTransaction]:
        """
        Fetches all transactions for a given security in a portfolio,
        optionally excluding one by its transaction_id.
        """
        stmt = select(DBTransaction).filter_by(
            portfolio_id=portfolio_id,
            security_id=security_id
        )

        if exclude_id:
            stmt = stmt.filter(DBTransaction.transaction_id != exclude_id)
            
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_transaction_costs(self, transaction_result: EngineTransaction) -> DBTransaction | None:
        """Finds a transaction by its ID and updates its calculated cost fields."""
        stmt = select(DBTransaction).filter_by(transaction_id=transaction_result.transaction_id)
        result = await self.db.execute(stmt)
        db_txn_to_update = result.scalars().first()

        if db_txn_to_update:
            db_txn_to_update.net_cost = transaction_result.net_cost
            db_txn_to_update.gross_cost = transaction_result.gross_cost
            db_txn_to_update.realized_gain_loss = transaction_result.realized_gain_loss
            db_txn_to_update.transaction_fx_rate = transaction_result.transaction_fx_rate
            db_txn_to_update.net_cost_local = transaction_result.net_cost_local
            db_txn_to_update.realized_gain_loss_local = transaction_result.realized_gain_loss_local
        
        return db_txn_to_update

    async def upsert_buy_lot_state(self, transaction_result: EngineTransaction) -> None:
        """Persists BUY lot state as a durable, idempotent record."""
        accrued_interest_local = getattr(transaction_result, "accrued_interest", None) or Decimal(0)
        lot_payload = {
            "lot_id": f"LOT-{transaction_result.transaction_id}",
            "source_transaction_id": transaction_result.transaction_id,
            "portfolio_id": transaction_result.portfolio_id,
            "instrument_id": transaction_result.instrument_id,
            "security_id": transaction_result.security_id,
            "acquisition_date": transaction_result.transaction_date.date(),
            "original_quantity": transaction_result.quantity,
            "open_quantity": transaction_result.quantity,
            "lot_cost_local": transaction_result.net_cost_local or Decimal(0),
            "lot_cost_base": transaction_result.net_cost or Decimal(0),
            "accrued_interest_paid_local": accrued_interest_local,
            "economic_event_id": getattr(transaction_result, "economic_event_id", None),
            "linked_transaction_group_id": getattr(transaction_result, "linked_transaction_group_id", None),
            "calculation_policy_id": getattr(transaction_result, "calculation_policy_id", None),
            "calculation_policy_version": getattr(transaction_result, "calculation_policy_version", None),
            "source_system": getattr(transaction_result, "source_system", None),
        }
        stmt = pg_insert(PositionLotState).values(**lot_payload)
        update_dict = {c.name: c for c in stmt.excluded if c.name not in ["id", "lot_id", "source_transaction_id"]}
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["source_transaction_id"], set_=update_dict)
        )

    async def upsert_accrued_income_offset_state(self, transaction_result: EngineTransaction) -> None:
        """Initializes or updates accrued-income offset state for BUY transactions."""
        accrued_interest_local = getattr(transaction_result, "accrued_interest", None) or Decimal(0)
        payload = {
            "offset_id": f"AIO-{transaction_result.transaction_id}",
            "source_transaction_id": transaction_result.transaction_id,
            "portfolio_id": transaction_result.portfolio_id,
            "instrument_id": transaction_result.instrument_id,
            "security_id": transaction_result.security_id,
            "accrued_interest_paid_local": accrued_interest_local,
            "remaining_offset_local": accrued_interest_local,
            "economic_event_id": getattr(transaction_result, "economic_event_id", None),
            "linked_transaction_group_id": getattr(transaction_result, "linked_transaction_group_id", None),
            "calculation_policy_id": getattr(transaction_result, "calculation_policy_id", None),
            "calculation_policy_version": getattr(transaction_result, "calculation_policy_version", None),
            "source_system": getattr(transaction_result, "source_system", None),
        }
        stmt = pg_insert(AccruedIncomeOffsetState).values(**payload)
        update_dict = {
            c.name: c
            for c in stmt.excluded
            if c.name not in ["id", "offset_id", "source_transaction_id"]
        }
        await self.db.execute(
            stmt.on_conflict_do_update(index_elements=["source_transaction_id"], set_=update_dict)
        )
