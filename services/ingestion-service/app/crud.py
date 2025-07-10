from sqlalchemy.orm import Session
from app.models.transaction import Transaction as PydanticTransaction
from app.database import TransactionDB

def create_transaction(db: Session, transaction: PydanticTransaction):
    db_transaction = TransactionDB(
        transaction_id=transaction.transaction_id,
        portfolio_id=transaction.portfolio_id,
        instrument_id=transaction.instrument_id,
        transaction_date=transaction.transaction_date,
        transaction_type=transaction.transaction_type,
        quantity=transaction.quantity,
        price=transaction.price,
        currency=transaction.currency,
        trade_fee=transaction.trade_fee,
        settlement_date=transaction.settlement_date,
        created_at=transaction.created_at
    )
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction

