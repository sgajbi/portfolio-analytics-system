import logging
from datetime import date
from decimal import Decimal
from typing import List, Dict

from portfolio_common.database_models import (
    PortfolioTimeseries, 
    PositionTimeseries, 
    Cashflow, 
    Instrument,
    Portfolio,
    FxRate
)

logger = logging.getLogger(__name__)

# NEW: Define a custom, specific exception for this failure case.
class FxRateNotFoundError(Exception):
    """Raised when a required FX rate for a calculation is not found."""
    pass

class PortfolioTimeseriesLogic:
    """
    A stateless calculator for aggregating position data into a single daily
    portfolio time series record, handling all necessary FX conversions.
    """
    @staticmethod
    def calculate_daily_record(
        portfolio: Portfolio,
        a_date: date,
        position_timeseries_list: List[PositionTimeseries],
        portfolio_cashflows: List[Cashflow],
        instruments: Dict[str, Instrument],
        fx_rates: Dict[str, FxRate]
    ) -> PortfolioTimeseries:
        """
        Calculates a single, complete portfolio time series record for a given day.
        """
        total_bod_mv = Decimal(0)
        total_bod_cf = Decimal(0)
        total_eod_cf = Decimal(0)
        total_eod_mv = Decimal(0)

        portfolio_currency = portfolio.base_currency

        # 1. Aggregate all position-level data with FX conversion
        for pos_ts in position_timeseries_list:
            instrument = instruments.get(pos_ts.security_id)
            if not instrument:
                logger.warning(f"Could not find instrument {pos_ts.security_id}. Skipping its contribution.")
                continue

            instrument_currency = instrument.currency
            rate = Decimal(1.0) # Default to 1.0 if no conversion is needed

            if instrument_currency != portfolio_currency:
                fx_rate = fx_rates.get(instrument_currency)
                if not fx_rate:
                    # FIX: Instead of just logging, raise a specific error to allow for retries.
                    error_msg = f"Missing FX rate from {instrument_currency} to {portfolio_currency} for date {pos_ts.date}. Cannot convert."
                    logger.error(error_msg)
                    raise FxRateNotFoundError(error_msg)
                rate = fx_rate.rate

            total_bod_mv += pos_ts.bod_market_value * rate
            total_bod_cf += pos_ts.bod_cashflow * rate
            total_eod_cf += pos_ts.eod_cashflow * rate
            total_eod_mv += pos_ts.eod_market_value * rate

        # 2. Aggregate portfolio-level cashflows (already in portfolio currency)
        for port_cf in portfolio_cashflows:
            if port_cf.timing == 'BOD':
                total_bod_cf += port_cf.amount
            elif port_cf.timing == 'EOD':
                total_eod_cf += port_cf.amount

        # Extract fees from portfolio-level cashflows
        total_fees = sum(cf.amount for cf in portfolio_cashflows if cf.classification == 'EXPENSE')

        return PortfolioTimeseries(
            portfolio_id=portfolio.portfolio_id,
            date=a_date,
            bod_market_value=total_bod_mv,
            bod_cashflow=total_bod_cf,
            eod_cashflow=total_eod_cf,
            eod_market_value=total_eod_mv,
            fees=abs(total_fees) # Fees are stored as a positive value
        )