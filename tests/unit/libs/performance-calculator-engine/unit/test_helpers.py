# tests/unit/libs/financial-calculator-engine/unit/test_helpers.py
import pytest
from datetime import date
from dateutil.relativedelta import relativedelta

from performance_calculator_engine.helpers import resolve_period, calculate_annualized_return

@pytest.fixture
def sample_dates():
    return {
        "inception_date": date(2022, 1, 15),
        "as_of_date": date(2025, 8, 13)
    }

# --- Tests for resolve_period ---

def test_resolve_period_explicit(sample_dates):
    name, start, end = resolve_period(
        period_type="EXPLICIT",
        from_date=date(2025, 1, 1),
        to_date=date(2025, 1, 31),
        **sample_dates
    )
    assert name == "EXPLICIT"
    assert start == date(2025, 1, 1)
    assert end == date(2025, 1, 31)

def test_resolve_period_ytd(sample_dates):
    name, start, end = resolve_period(period_type="YTD", **sample_dates)
    assert name == "YTD"
    assert start == date(2025, 1, 1)
    assert end == date(2025, 8, 13)

def test_resolve_period_mtd(sample_dates):
    name, start, end = resolve_period(period_type="MTD", **sample_dates)
    assert name == "MTD"
    assert start == date(2025, 8, 1)
    assert end == date(2025, 8, 13)

def test_resolve_period_qtd(sample_dates):
    name, start, end = resolve_period(period_type="QTD", **sample_dates)
    assert name == "QTD"
    assert start == date(2025, 7, 1)
    assert end == date(2025, 8, 13)

def test_resolve_period_three_year(sample_dates):
    name, start, end = resolve_period(period_type="THREE_YEAR", **sample_dates)
    assert name == "THREE_YEAR"
    assert start == date(2022, 8, 14)
    assert end == date(2025, 8, 13)

def test_resolve_period_si(sample_dates):
    name, start, end = resolve_period(period_type="SI", **sample_dates)
    assert name == "SI"
    assert start == sample_dates["inception_date"]
    assert end == sample_dates["as_of_date"]

def test_resolve_period_respects_inception_date(sample_dates):
    # THREE_YEAR start date (2022-08-14) is after inception (2022-01-15)
    _, start, _ = resolve_period(period_type="THREE_YEAR", **sample_dates)
    assert start == date(2022, 8, 14)

    # FIVE_YEAR start date (2020-08-14) is before inception (2022-01-15), so it should be capped
    _, start, _ = resolve_period(period_type="FIVE_YEAR", **sample_dates)
    assert start == sample_dates["inception_date"]

def test_resolve_period_raises_for_missing_args():
    with pytest.raises(ValueError, match="ExplicitPeriod requires"):
        resolve_period(period_type="EXPLICIT", inception_date=date(2020,1,1), as_of_date=date(2022,1,1))
    with pytest.raises(ValueError, match="YearPeriod requires"):
        resolve_period(period_type="YEAR", inception_date=date(2020,1,1), as_of_date=date(2022,1,1))

# --- Tests for calculate_annualized_return ---

def test_annualized_return_for_long_period():
    # 2 years period (731 days including a leap year)
    result = calculate_annualized_return(21, date(2023, 1, 1), date(2024, 12, 31))
    assert result is not None
    # FIX: Use the precise calculated value for the assertion
    assert pytest.approx(result) == 9.99282915

def test_annualized_return_for_short_period():
    # Less than 1 year period
    result = calculate_annualized_return(5, date(2024, 1, 1), date(2024, 6, 30))
    assert result is None

def test_annualized_return_for_exactly_one_year():
    # A full leap year (366 days) should not be annualized
    result = calculate_annualized_return(8, date(2024, 1, 1), date(2024, 12, 31))
    assert result is None

def test_annualized_return_for_loss():
    # 3 years period with a loss (1096 days)
    result = calculate_annualized_return(-15, date(2022, 1, 1), date(2024, 12, 31))
    assert result is not None
    # FIX: Use the precise calculated value for the assertion
    assert pytest.approx(result, abs=1e-4) == -5.2720