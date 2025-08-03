# services/persistence_service/app/repositories/portfolio_repository.py
import logging
from sqlalchemy.orm import Session
from portfolio_common.database_models import Portfolio as DBPortfolio
from portfolio_common.events import PortfolioEvent

logger = logging.getLogger(__name__)

class PortfolioRepository:
    """
    Handles database operations for the Portfolio model.
    """
    def __init__(self, db: Session):
        self.db = db

    def create_or_update_portfolio(self, event: PortfolioEvent) -> DBPortfolio:
        """
        Idempotently creates a new portfolio or updates an existing one
        using a get-then-update/create pattern.
        """
        try:
            db_portfolio = self.db.query(DBPortfolio).filter(DBPortfolio.portfolio_id == event.portfolio_id).first()
            
            # Use model_dump() without by_alias to get Python-native field names
            portfolio_data = event.model_dump()

            if db_portfolio:
                # Update existing record
                for key, value in portfolio_data.items():
                    setattr(db_portfolio, key, value)
                logger.info(f"Portfolio '{event.portfolio_id}' found, staging for update.")
            else:
                # Create new record
                db_portfolio = DBPortfolio(**portfolio_data)
                self.db.add(db_portfolio)
                logger.info(f"Portfolio '{event.portfolio_id}' not found, staging for creation.")
            
            return db_portfolio
        except Exception as e:
            logger.error(f"Failed to stage upsert for portfolio '{event.portfolio_id}': {e}", exc_info=True)
            raise