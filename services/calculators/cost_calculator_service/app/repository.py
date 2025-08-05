# services/calculators/cost_calculator_service/app/repository.py
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from portfolio_common.database_models import Transaction as DBTransaction
from core.models.transaction import Transaction as EngineTransaction

class CostCalculatorRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

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
        
        return db_txn_to_update