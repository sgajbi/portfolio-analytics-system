# src/libs/performance-calculator-engine/src/performance_calculator_engine/helpers.py
from datetime import date, timedelta
from typing import Tuple, Optional
from dateutil.relativedelta import relativedelta

# Note: The DTOs are defined in the query-service, so we cannot import them here.
# This helper will work with primitive types passed from the service.

def resolve_period(
    period_type: str,
    inception_date: date,
    as_of_date: date,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    year: Optional[int] = None,
    name: Optional[str] = None
) -> Tuple[str, date, date]:
    """
    Translates a symbolic or explicit period into a concrete start and end date.
    """
    period_name = name or year or period_type
    start_date, end_date = date.max, date.min

    if period_type == "EXPLICIT":
        if from_date is None or to_date is None:
            raise ValueError("ExplicitPeriod requires 'from_date' and 'to_date'.")
        start_date, end_date = from_date, to_date
    elif period_type == "YEAR":
        if year is None:
            raise ValueError("YearPeriod requires 'year'.")
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
    else: # Standard Periods
        end_date = as_of_date
        if period_type == "YTD":
            start_date = date(as_of_date.year, 1, 1)
        elif period_type == "QTD":
            quarter_month = (as_of_date.month - 1) // 3 * 3 + 1
            start_date = date(as_of_date.year, quarter_month, 1)
        elif period_type == "MTD":
            start_date = date(as_of_date.year, as_of_date.month, 1)
        elif period_type == "THREE_YEAR":
            start_date = as_of_date - relativedelta(years=3) + timedelta(days=1)
        elif period_type == "FIVE_YEAR":
            start_date = as_of_date - relativedelta(years=5) + timedelta(days=1)
        elif period_type == "SI":
            start_date = inception_date
    
    # Ensure the calculation doesn't start before the portfolio existed
    final_start_date = max(start_date, inception_date)
    return str(period_name), final_start_date, end_date

def calculate_annualized_return(cumulative_return: float, start_date: date, end_date: date) -> Optional[float]:
    """
    Calculates the annualized return for a given cumulative return over a period.
    Returns the cumulative_return if the period is one year or less.
    """
    days = (end_date - start_date).days + 1
    if days <= 366:
        return cumulative_return
    
    years = days / 365.25
    
    # Formula: ((1 + CumulativeReturn) ^ (1 / Years)) - 1
    base = 1 + cumulative_return / 100
    if base < 0:
        # Cannot take a root of a negative number, annualized return is not meaningful
        return None
        
    return ((base ** (1 / years)) - 1) * 100