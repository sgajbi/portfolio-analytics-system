from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.analytics_input_dto import (
    PortfolioAnalyticsTimeseriesRequest,
    PositionAnalyticsTimeseriesRequest,
)


def test_portfolio_timeseries_request_requires_window_or_period() -> None:
    with pytest.raises(ValidationError):
        PortfolioAnalyticsTimeseriesRequest(as_of_date="2025-12-31")


def test_position_timeseries_request_requires_window_or_period() -> None:
    with pytest.raises(ValidationError):
        PositionAnalyticsTimeseriesRequest(as_of_date="2025-12-31")
