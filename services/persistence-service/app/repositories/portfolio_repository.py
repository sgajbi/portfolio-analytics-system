import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from portfolio_common.database_models import Portfolio as DBPortfolio
from portfolio_common.events import PortfolioEvent # This event will be created next

logger = logging.getLogger(__name__)

class PortfolioRepository:
    """
    Handles database operations for the Portfolio model.
    """
    def __init__(self, db: Session):
        self.db = db

    def create_or_update_portfolio(self, event: PortfolioEvent) -> DBPortfolio:
        """
        Creates a new portfolio or updates an existing one based on portfolio_id.
        This operation is idempotent.
        """
        existing_portfolio = self.db.query(DBPortfolio).filter(
            DBPortfolio.portfolio_id == event.portfolio_id
        ).first()

        if existing_portfolio:
            logger.info(f"Portfolio '{event.portfolio_id}' already exists. Updating record.")
            # Update existing record
            for key, value in event.model_dump().items():
                setattr(existing_portfolio, key, value)
            db_portfolio = existing_portfolio
        else:
            logger.info(f"Creating new portfolio record for '{event.portfolio_id}'.")
            # Create a new portfolio if it doesn't exist
            db_portfolio = DBPortfolio(**event.model_dump())

        try:
            self.db.add(db_portfolio)
            self.db.commit()
            self.db.refresh(db_portfolio)
            logger.info(f"Portfolio '{db_portfolio.portfolio_id}' successfully saved to DB.")
            return db_portfolio
        except IntegrityError:
            self.db.rollback()
            logger.warning(f"Race condition: Portfolio '{event.portfolio_id}' was inserted by another process. Fetching existing.")
            return self.db.query(DBPortfolio).filter(
                DBPortfolio.portfolio_id == event.portfolio_id
            ).first()