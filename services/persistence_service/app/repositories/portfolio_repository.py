import logging
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

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
        Idempotently creates a new portfolio or updates an existing one based on portfolio_id.
        This operation leverages PostgreSQL's ON CONFLICT DO UPDATE (UPSERT).
        """
        insert_dict = {
            "portfolio_id": event.portfolio_id,
            "base_currency": event.base_currency,
            "open_date": event.open_date,
            "close_date": event.close_date,
            "risk_exposure": event.risk_exposure,
            "investment_time_horizon": event.investment_time_horizon,
            "portfolio_type": event.portfolio_type,
            "objective": event.objective,
            "booking_center": event.booking_center,
            "cif_id": event.cif_id,
            "is_leverage_allowed": event.is_leverage_allowed,
            "advisor_id": event.advisor_id,
            "status": event.status,
        }

        stmt = pg_insert(DBPortfolio).values(**insert_dict)
        
        on_conflict_stmt = stmt.on_conflict_do_update(
            index_elements=['portfolio_id'],
            set_={
                'base_currency': stmt.excluded.base_currency,
                'open_date': stmt.excluded.open_date,
                'close_date': stmt.excluded.close_date,
                'risk_exposure': stmt.excluded.risk_exposure,
                'investment_time_horizon': stmt.excluded.investment_time_horizon,
                'portfolio_type': stmt.excluded.portfolio_type,
                'objective': stmt.excluded.objective,
                'booking_center': stmt.excluded.booking_center,
                'cif_id': stmt.excluded.cif_id,
                'is_leverage_allowed': stmt.excluded.is_leverage_allowed,
                'advisor_id': stmt.excluded.advisor_id,
                'status': stmt.excluded.status,
                'updated_at': stmt.excluded.updated_at
            }
        ).returning(DBPortfolio)

        try:
            result = self.db.execute(on_conflict_stmt).scalar_one()
            # COMMIT AND ROLLBACK REMOVED - Handled by the service layer.
            logger.info(f"Portfolio '{result.portfolio_id}' successfully staged for upsert.")
            return result
        except Exception as e:
            # Rollback is handled by the service layer's context manager.
            logger.error(f"Failed to stage upsert for portfolio '{event.portfolio_id}': {e}", exc_info=True)
            raise