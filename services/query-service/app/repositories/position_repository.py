import logging
from datetime import date
from typing import List, Any, Optional

from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, desc

from portfolio_common.database_models import PositionHistory, Instrument

logger = logging.getLogger(__name__)

class PositionRepository:
    """
    Handles read-only database queries for position data.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_position_history_by_security(
        self,
        portfolio_id: str,
        security_id: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[PositionHistory]:
        """
        Retrieves the time series of position history for a specific security,
        with optional date range filtering.
        """
        query = self.db.query(PositionHistory).filter(
            PositionHistory.portfolio_id == portfolio_id,
            PositionHistory.security_id == security_id
        )

        if start_date:
            query = query.filter(PositionHistory.position_date >= start_date)
        
        if end_date:
            query = query.filter(PositionHistory.position_date <= end_date)

        results = query.order_by(PositionHistory.position_date.asc()).all()
        logger.info(
            f"Found {len(results)} position history records for security '{security_id}' "
            f"in portfolio '{portfolio_id}'."
        )
        return results

    def get_latest_positions_by_portfolio(self, portfolio_id: str) -> List[Any]:
        """
        Retrieves the single latest position for each security in a given portfolio.
        
        This uses a window function to rank position records for each security
        by date and then selects only the most recent one (rank=1). It also joins
        with the Instrument table to fetch the instrument's name.
        """
        
        # Subquery to rank positions for each security by date
        ranked_positions_subq = self.db.query(
            PositionHistory,
            func.row_number().over(
                partition_by=PositionHistory.security_id,
                order_by=[
                    PositionHistory.position_date.desc(),
                    PositionHistory.id.desc() # Tie-breaker for same-day transactions
                ]
            ).label('rn')
        ).filter(
            PositionHistory.portfolio_id == portfolio_id
        ).subquery('ranked_positions')

        ranked_positions = aliased(PositionHistory, ranked_positions_subq)

        # Main query to select the latest position object (where rank is 1)
        # and LEFT JOIN with Instruments to get the name.
        results = self.db.query(
            ranked_positions, # Select the entire ranked position object
            Instrument.name.label('instrument_name')
        ).outerjoin( # Use outerjoin to be more robust
            Instrument, Instrument.security_id == ranked_positions.security_id
        ).filter(
            ranked_positions_subq.c.rn == 1,
            # Also filter out zero-quantity positions, as they are closed
            ranked_positions.quantity > 0 
        ).all()

        logger.info(f"Found {len(results)} latest positions for portfolio '{portfolio_id}'.")
        return results