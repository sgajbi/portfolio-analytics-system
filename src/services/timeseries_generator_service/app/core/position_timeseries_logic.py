from datetime import date
from decimal import Decimal

from portfolio_common.database_models import PositionTimeseries, DailyPositionSnapshot

class PositionTimeseriesLogic:
    """
    A stateless calculator for generating a single daily position time series record.
    """
    @staticmethod
    def calculate_daily_record(
        current_snapshot: DailyPositionSnapshot,
        previous_timeseries: PositionTimeseries | None,
        bod_cashflow: Decimal,
        eod_cashflow: Decimal
    ) -> PositionTimeseries:
        """
        Calculates a single, complete position time series record for a given day.
        Args:
            current_snapshot: The DailyPositionSnapshot record for the date being calculated.
            previous_timeseries: The PositionTimeseries record for the previous day.
            bod_cashflow: The sum of all beginning-of-day cashflows for the position.
            eod_cashflow: The sum of all end-of-day cashflows for the position.
        Returns:
            A populated PositionTimeseries database model instance.
        """
        bod_market_value = previous_timeseries.eod_market_value if previous_timeseries else Decimal(0)

        eod_market_value = current_snapshot.market_value_local or Decimal(0)
        eod_quantity = current_snapshot.quantity
        eod_cost_basis = current_snapshot.cost_basis

        eod_avg_cost = (eod_cost_basis / eod_quantity) if eod_quantity else Decimal(0)

        return PositionTimeseries(
            portfolio_id=current_snapshot.portfolio_id,
            security_id=current_snapshot.security_id,
            date=current_snapshot.date,
            bod_market_value=bod_market_value,
            bod_cashflow=bod_cashflow,
            eod_cashflow=eod_cashflow,
            eod_market_value=eod_market_value,
            fees=Decimal(0),
            quantity=eod_quantity,
            cost=eod_avg_cost
        )