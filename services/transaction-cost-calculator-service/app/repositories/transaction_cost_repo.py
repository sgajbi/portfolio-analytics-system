import logging
from sqlalchemy.orm import Session
from sqlalchemy import exc
from common.models import Transaction, TransactionCost
from common.db import SessionLocal
from typing import Optional
from datetime import date

logger = logging.getLogger(__name__)

class TransactionCostRepository:
    def __init__(self, db_session: Optional[Session] = None):
        self.db_session = db_session

    def create_transaction_cost(
        self,
        transaction_id: str,
        portfolio_id: str,
        instrument_id: str,
        transaction_date: date,
        cost_amount: float,
        cost_currency: str
    ) -> Optional[TransactionCost]:
        """
        Creates a new transaction cost entry in the database.
        It links to the transaction using the business key fields.
        """
        session = self.db_session if self.db_session else SessionLocal()
        try:
            # Check if an entry for this exact transaction already exists to prevent duplicates
            existing_cost = session.query(TransactionCost).filter(
                TransactionCost.transaction_id == transaction_id,
                TransactionCost.portfolio_id == portfolio_id,
                TransactionCost.instrument_id == instrument_id,
                TransactionCost.transaction_date == transaction_date
            ).first()

            if existing_cost:
                logger.info(f"Transaction cost for '{transaction_id}' on '{transaction_date}' already recorded. Skipping.")
                return existing_cost

            new_cost = TransactionCost(
                transaction_id=transaction_id,
                portfolio_id=portfolio_id,
                instrument_id=instrument_id,
                transaction_date=transaction_date,
                cost_amount=cost_amount,
                cost_currency=cost_currency
            )
            session.add(new_cost)
            session.commit()
            session.refresh(new_cost)
            logger.info(f"Transaction cost for '{transaction_id}' on '{transaction_date}' inserted into DB with amount {cost_amount} {cost_currency}.")
            return new_cost
        except exc.IntegrityError:
            session.rollback()
            logger.warning(f"Integrity error creating transaction cost for '{transaction_id}' on '{transaction_date}'. May indicate a race condition or existing unique constraint violation.")
            return None
        except Exception as e:
            session.rollback()
            logger.error(f"Error creating transaction cost for '{transaction_id}' on '{transaction_date}': {e}", exc_info=True)
            return None
        finally:
            if not self.db_session:
                session.close()