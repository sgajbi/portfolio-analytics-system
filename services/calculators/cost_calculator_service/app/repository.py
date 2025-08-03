# services/calculators/cost_calculator_service/app/repository.py
from typing import List, Optional
from sqlalchemy.orm import Session
from portfolio_common.database_models import Transaction as DBTransaction
from core.models.transaction import Transaction as EngineTransaction

class CostCalculatorRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_transaction_history(
        self,
        portfolio_id: str,
        security_id: str,
        exclude_id: Optional[str] = None
    ) -> List[DBTransaction]:
        """
        Fetches all transactions for a given security in a portfolio,
        optionally excluding one by its transaction_id.
        """
        query = self.db.query(DBTransaction).filter(
            DBTransaction.portfolio_id == portfolio_id,
            DBTransaction.security_id == security_id
        )

        if exclude_id:
            query = query.filter(DBTransaction.transaction_id != exclude_id)
            
        return query.all()

    def update_transaction_costs(self, transaction_result: EngineTransaction) -> DBTransaction | None:
        """Finds a transaction by its ID and updates its calculated cost fields."""
        db_txn_to_update = self.db.query(DBTransaction).filter(
            DBTransaction.transaction_id == transaction_result.transaction_id
        ).first()

        if db_txn_to_update:
            db_txn_to_update.net_cost = transaction_result.net_cost
            db_txn_to_update.gross_cost = transaction_result.gross_cost
            db_txn_to_update.realized_gain_loss = transaction_result.realized_gain_loss
        
        return db_txn_to_update