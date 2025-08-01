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
            # Attempt to get the existing record
            db_portfolio = self.db.query(DBPortfolio).filter(DBPortfolio.portfolio_id == event.portfolio_id).first()

            if db_portfolio:
                # Update existing record
                db_portfolio.base_currency = event.base_currency
                db_portfolio.open_date = event.open_date
                db_portfolio.close_date = event.close_date
                db_portfolio.risk_exposure = event.risk_exposure
                db_portfolio.investment_time_horizon = event.investment_time_horizon
                db_portfolio.portfolio_type = event.portfolio_type
                db_portfolio.objective = event.objective
                db_portfolio.booking_center = event.booking_center
                db_portfolio.cif_id = event.cif_id
                db_portfolio.is_leverage_allowed = event.is_leverage_allowed
                db_portfolio.advisor_id = event.advisor_id
                db_portfolio.status = event.status
                logger.info(f"Portfolio '{event.portfolio_id}' found, staging for update.")
            else:
                # Create new record
                db_portfolio = DBPortfolio(**event.model_dump())
                self.db.add(db_portfolio)
                logger.info(f"Portfolio '{event.portfolio_id}' not found, staging for creation.")
            
            return db_portfolio
        except Exception as e:
            logger.error(f"Failed to stage upsert for portfolio '{event.portfolio_id}': {e}", exc_info=True)
            raise