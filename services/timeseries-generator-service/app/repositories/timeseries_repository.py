import logging
from datetime import date, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from portfolio_common.database_models import (
    PositionTimeseries, 
    PortfolioTimeseries, 
    Portfolio, 
    Cashflow, 
    FxRate,
    Instrument
)

logger = logging.getLogger(__name__)

class TimeseriesRepository:
    """
    Handles all database read/write operations for time series data.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_portfolio(self, portfolio_id: str) -> Optional[Portfolio]:
        """Fetches portfolio details by its ID."""
        return self.db.query(Portfolio).filter(Portfolio.portfolio_id == portfolio_id).first()

    def get_fx_rate(self, from_currency: str, to_currency: str, a_date: date) -> Optional[FxRate]:
        """Fetches the latest FX rate on or before a given date."""
        return self.db.query(FxRate).filter(
            FxRate.from_currency == from_currency,
            FxRate.to_currency == to_currency,
            FxRate.rate_date <= a_date
        ).order_by(FxRate.rate_date.desc()).first()

    def get_last_position_timeseries_before(
        self,
        portfolio_id: str,
        security_id: str,
        a_date: date
    ) -> Optional[PositionTimeseries]:
        """
        Fetches the most recent position time series record for a security
        strictly before a given date.
        """
        return self.db.query(PositionTimeseries).filter(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.security_id == security_id,
            PositionTimeseries.date < a_date
        ).order_by(PositionTimeseries.date.desc()).first()

    def get_all_position_timeseries_for_date(
        self, portfolio_id: str, a_date: date
    ) -> List[PositionTimeseries]:
        """Fetches all position time series records for a portfolio on a specific date."""
        return self.db.query(PositionTimeseries).filter(
            PositionTimeseries.portfolio_id == portfolio_id,
            PositionTimeseries.date == a_date
        ).all()

    def get_portfolio_level_cashflows_for_date(self, portfolio_id: str, a_date: date) -> List[Cashflow]:
        """Fetches all portfolio-level cashflows for a specific date."""
        return self.db.query(Cashflow).filter(
            Cashflow.portfolio_id == portfolio_id,
            Cashflow.cashflow_date == a_date,
            Cashflow.level == 'PORTFOLIO'
        ).all()

    def upsert_position_timeseries(self, timeseries_record: PositionTimeseries):
        """Idempotent insert/update for a position time series record."""
        try:
            # Create a dictionary of the record's values, excluding SQLAlchemy state
            values = {c.name: getattr(timeseries_record, c.name) for c in timeseries_record.__table__.columns}
            stmt = pg_insert(PositionTimeseries).values(
                **values
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'security_id', 'date'],
                set_=values
            )
            self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Upserted position time series for {timeseries_record.security_id} on {timeseries_record.date}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to upsert position time series: {e}", exc_info=True)
            raise
    
    def upsert_portfolio_timeseries(self, timeseries_record: PortfolioTimeseries):
        """Idempotent insert/update for a portfolio time series record."""
        try:
            # Create a dictionary of the record's values, excluding SQLAlchemy state
            values = {c.name: getattr(timeseries_record, c.name) for c in timeseries_record.__table__.columns}
            stmt = pg_insert(PortfolioTimeseries).values(
                **values
            ).on_conflict_do_update(
                index_elements=['portfolio_id', 'date'],
                set_=values
            )
            self.db.execute(stmt)
            self.db.commit()
            logger.info(f"Upserted portfolio time series for {timeseries_record.portfolio_id} on {timeseries_record.date}")
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to upsert portfolio time series: {e}", exc_info=True)
            raise