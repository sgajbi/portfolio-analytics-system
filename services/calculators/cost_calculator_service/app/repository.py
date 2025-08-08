# services/calculators/cost_calculator_service/app/repository.py
from typing import List, Optional
from datetime import date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Transaction as DBTransaction, Portfolio, FxRate
from core.models.transaction import Transaction as EngineTransaction

class CostCalculatorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches a portfolio by its ID."""
        return await self.db.get(Portfolio, portfolio_id)

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