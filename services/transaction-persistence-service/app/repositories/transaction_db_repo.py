from sqlalchemy.orm import Session
from common.database_models import TransactionDB
from app.models.transaction_event import TransactionEvent

class TransactionDBRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_transaction(self, transaction_event: TransactionEvent) -> TransactionDB:
        """
        Saves a new transaction event to the PostgreSQL database.
        """
        db_transaction = TransactionDB(
            transaction_id=transaction_event.transaction_id,
            portfolio_id=transaction_event.portfolio_id,
            instrument_id=transaction_event.instrument_id,
            transaction_date=transaction_event.transaction_date,
            transaction_type=transaction_event.transaction_type,
            quantity=transaction_event.quantity,
            price=transaction_event.price,
            currency=transaction_event.currency,
            trade_fee=transaction_event.trade_fee,
            settlement_date=transaction_event.settlement_date,
            created_at=transaction_event.created_at
        )
        self.db.add(db_transaction)
        self.db.commit()
        self.db.refresh(db_transaction)
        return db_transaction

