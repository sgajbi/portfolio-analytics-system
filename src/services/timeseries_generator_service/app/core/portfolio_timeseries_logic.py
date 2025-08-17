# src/services/timeseries_generator_service/app/core/portfolio_timeseries_logic.py
import logging
from datetime import date
from decimal import Decimal
from typing import List, Dict

from portfolio_common.database_models import (
    PortfolioTimeseries, 
    PositionTimeseries, 
    Cashflow, 
    Portfolio,
)
from portfolio_common.repositories.timeseries_repository import TimeseriesRepository

logger = logging.getLogger(__name__)

class FxRateNotFoundError(Exception):
    """Raised when a required FX rate for a calculation is not found."""
    pass

class PortfolioTimeseriesLogic:
    """
    A stateless calculator for aggregating position data into a single daily
    portfolio time series record, handling all necessary FX conversions.
    """
    @staticmethod
    async def calculate_daily_record(
        portfolio: Portfolio,
        a_date: date,
        position_timeseries_list: List[PositionTimeseries],
        portfolio_cashflows: List[Cashflow],
        repo: TimeseriesRepository
    ) -> PortfolioTimeseries:
        """
        Calculates a single, complete portfolio time series record for a given day.
        """
        total_bod_mv = Decimal(0)
        total_bod_cf = Decimal(0)
        total_eod_cf = Decimal(0)
        total_eod_mv = Decimal(0)

        portfolio_currency = portfolio.base_currency

        previous_portfolio_ts = await repo.get_last_portfolio_timeseries_before(portfolio.portfolio_id, a_date)
        if previous_portfolio_ts:
            total_bod_mv = previous_portfolio_ts.eod_market_value
        else:
            total_bod_mv = Decimal(0)

        security_ids = [pt.security_id for pt in position_timeseries_list]
        instruments_list = await repo.get_instruments_by_ids(security_ids)
        instruments = {inst.security_id: inst for inst in instruments_list}

        for pos_ts in position_timeseries_list:
            instrument = instruments.get(pos_ts.security_id)
            if not instrument:
                logger.warning(f"Could not find instrument {pos_ts.security_id}. Skipping its contribution.")
                continue

            instrument_currency = instrument.currency
            rate = Decimal(1.0)

            if instrument_currency != portfolio_currency:
                fx_rate = await repo.get_fx_rate(instrument_currency, portfolio_currency, pos_ts.date)
                if not fx_rate:
                    error_msg = f"Missing FX rate from {instrument_currency} to {portfolio_currency} for date {pos_ts.date}. Cannot convert."
                    logger.error(error_msg)
                    raise FxRateNotFoundError(error_msg)
                rate = fx_rate.rate

            # FIX: Defensively treat None as 0
            total_bod_cf += (pos_ts.bod_cashflow or Decimal(0)) * rate
            total_eod_cf += (pos_ts.eod_cashflow or Decimal(0)) * rate
            total_eod_mv += (pos_ts.eod_market_value or Decimal(0)) * rate

        for port_cf in portfolio_cashflows:
            if port_cf.timing == 'BOD':
                total_bod_cf += port_cf.amount
            elif port_cf.timing == 'EOD':
                total_eod_cf += port_cf.amount

        total_fees = sum(cf.amount for cf in portfolio_cashflows if cf.classification == 'EXPENSE')

        return PortfolioTimeseries(
            portfolio_id=portfolio.portfolio_id,
            date=a_date,
            bod_market_value=total_bod_mv,
            bod_cashflow=total_bod_cf,
            eod_cashflow=total_eod_cf,
            eod_market_value=total_eod_mv,
            fees=abs(total_fees)
        )