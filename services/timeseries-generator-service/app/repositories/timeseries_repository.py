import logging
from datetime import date, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import PositionTimeseries, PortfolioTimeseries

logger = logging.getLogger(__name__)

class TimeseriesRepository:
    """
    Handles all database read/write operations for time series data.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_last_position_timeseries_before(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date
    ) -> Optional[PositionTimeseries]:
        """
        Fetches the most recent position time series record for a security
        strictly before a given date. This serves as the starting point (BOD value).
        """
        return self.db.query(PositionTimeseries).filter(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date < a_date
        ).order_by(PositionTimeseries.date.desc()).first()

    def upsert_position_timeseries(self, timeseries_record: PositionTimeseries):
        """
        Inserts a new position time series record. If a record for the same
        portfolio, security, and date already exists, it updates it.
        """
        try:
            stmt = pg_insert(PositionTimeseries).values(
                timeseries_record.__dict__
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'security_id', 'date'],
                set_=timeseries_record.__dict__
            )
            self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Upserted position time series for {timeseries_record.security_id} on {timeseries_record.date}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to upsert position time series: {e}", exc_info=True)
            raise