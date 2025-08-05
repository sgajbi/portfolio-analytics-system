# services/persistence_service/app/repositories/transaction_db_repo.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from portfolio_common.database_models import Transaction as DBTransaction
from portfolio_common.events import TransactionEvent

logger = logging.getLogger(__name__)

class TransactionDBRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update_transaction(self, event: TransactionEvent) -> DBTransaction:
        """
        Idempotently creates or updates a transaction using a
        get-then-update/create pattern.
        """
        try:
            stmt = select(DBTransaction).filter_by(transaction_id=event.transaction_id)
            result = await self.db.execute(stmt)
            db_transaction = result.scalars().first()
            
            event_dict = event.model_dump()

            if db_transaction:
                for key, value in event_dict.items():
                    setattr(db_transaction, key, value)
                logger.info(f"Transaction '{event.transaction_id}' found, staging for update.")
            else:
                db_transaction = DBTransaction(**event_dict)
                self.db.add(db_transaction)
                logger.info(f"Transaction '{event.transaction_id}' not found, staging for creation.")

            return db_transaction
        except Exception as e:
            logger.error(f"Failed to stage upsert for transaction '{event.transaction_id}': {e}", exc_info=True)
            raise