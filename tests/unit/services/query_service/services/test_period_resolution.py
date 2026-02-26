from datetime import date
from types import SimpleNamespace

from src.services.query_service.app.services.period_resolution import resolve_request_periods


def test_resolve_request_periods_maps_year_to_calendar_window() -> None:
    periods = [SimpleNamespace(type="YEAR", name="FY24", year=2024)]

    resolved = resolve_request_periods(
        periods, inception_date=date(2020, 1, 1), as_of_date=date(2025, 3, 31)
    )

    assert resolved == [("FY24", date(2024, 1, 1), date(2024, 12, 31))]


def test_resolve_request_periods_uses_explicit_dates_when_provided() -> None:
    periods = [
        SimpleNamespace(
            type="EXPLICIT",
            name="Jan25",
            from_date=date(2025, 1, 1),
            to_date=date(2025, 1, 31),
            year=None,
        )
    ]

    resolved = resolve_request_periods(
        periods, inception_date=date(2020, 1, 1), as_of_date=date(2025, 3, 31)
    )

    assert resolved == [("Jan25", date(2025, 1, 1), date(2025, 1, 31))]
