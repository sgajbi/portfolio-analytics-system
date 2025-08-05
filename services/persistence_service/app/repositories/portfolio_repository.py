# services/persistence_service/app/repositories/portfolio_repository.py
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from portfolio_common.database_models import Portfolio as DBPortfolio
from portfolio_common.events import PortfolioEvent

logger = logging.getLogger(__name__)

class PortfolioRepository:
    """
    Handles database operations for the Portfolio model.
    """
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_or_update_portfolio(self, event: PortfolioEvent) -> DBPortfolio:
        """
        Idempotently creates a new portfolio or updates an existing one
        using a get-then-update/create pattern.
        """
        try:
            stmt = select(DBPortfolio).filter_by(portfolio_id=event.portfolio_id)
            result = await self.db.execute(stmt)
            db_portfolio = result.scalars().first()
            
            portfolio_data = event.model_dump()

            if db_portfolio:
                for key, value in portfolio_data.items():
                    setattr(db_portfolio, key, value)
                logger.info(f"Portfolio '{event.portfolio_id}' found, staging for update.")
            else:
                db_portfolio = DBPortfolio(**portfolio_data)
                self.db.add(db_portfolio)
                logger.info(f"Portfolio '{event.portfolio_id}' not found, staging for creation.")
            
            return db_portfolio
        except Exception as e:
            logger.error(f"Failed to stage upsert for portfolio '{event.portfolio_id}': {e}", exc_info=True)
            raise