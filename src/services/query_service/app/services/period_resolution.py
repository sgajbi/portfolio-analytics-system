from __future__ import annotations

from datetime import date
from typing import Any

from performance_calculator_engine.helpers import resolve_period


def resolve_request_periods(
    periods: list[Any], *, inception_date: date, as_of_date: date
) -> list[tuple[str, date, date]]:
    """Resolve request period DTOs into concrete (name, start, end) tuples.

    Shared helper to keep period resolution behavior consistent across
    query-service domains (performance, risk, and future analytics services).
    """
    resolved_periods: list[tuple[str, date, date]] = []

    for period in periods:
        from_date = getattr(period, "from_date", None)
        to_date = getattr(period, "to_date", None)
        year = getattr(period, "year", None)

        if period.type == "YEAR" and year is not None:
            from_date = date(year, 1, 1)
            to_date = date(year, 12, 31)

        resolved = resolve_period(
            period_type=period.type,
            name=period.name or period.type,
            from_date=from_date,
            to_date=to_date,
            year=year,
            inception_date=inception_date,
            as_of_date=as_of_date,
        )
        resolved_periods.append((resolved[0], resolved[1], resolved[2]))

    return resolved_periods
