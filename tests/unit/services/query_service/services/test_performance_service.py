# tests/unit/services/query_service/services/test_performance_service.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import date
from decimal import Decimal
import pandas as pd

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.performance_service import PerformanceService
from src.services.query_service.app.dtos.performance_dto import PerformanceRequest
from portfolio_common.database_models import Portfolio, PortfolioTimeseries

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_portfolio_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id.return_value = Portfolio(portfolio_id="P1", open_date=date(2020, 1, 1))
    return repo


@pytest.fixture
def mock_performance_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_portfolio_timeseries_for_range.return_value = [
        PortfolioTimeseries(
            date=date(2025, 1, 15),
            bod_market_value=1,
            eod_market_value=1,
            bod_cashflow=1,
            eod_cashflow=1,
            fees=1,
        )
    ]
    return repo


@pytest.fixture
def mock_performance_calculator() -> MagicMock:
    mock_calc = MagicMock()
    # Simulate the engine returning a DataFrame with a calculated result
    mock_df = pd.DataFrame(
        [
            {
                "final_cumulative_ror_pct": 5.5,
                "bod_market_value": Decimal("1000"),
                "eod_market_value": Decimal("1055"),
                "bod_cashflow": Decimal("0"),
                "eod_cashflow": Decimal("0"),
                "fees": Decimal("0"),
            }
        ]
    )
    mock_calc.return_value.calculate_performance.return_value = mock_df
    return mock_calc


@pytest.fixture
def service(mock_portfolio_repo: AsyncMock, mock_performance_repo: AsyncMock) -> PerformanceService:
    """Provides a PerformanceService instance with mocked repositories."""
    with (
        patch(
            "src.services.query_service.app.services.performance_service.PortfolioRepository",
            return_value=mock_portfolio_repo,
        ),
        patch(
            "src.services.query_service.app.services.performance_service.PerformanceRepository",
            return_value=mock_performance_repo,
        ),
    ):
        # The db session itself can be a simple mock as the repos are mocked
        return PerformanceService(AsyncMock(spec=AsyncSession))


async def test_calculate_performance_happy_path(
    service: PerformanceService,
    mock_portfolio_repo: AsyncMock,
    mock_performance_repo: AsyncMock,
    mock_performance_calculator: MagicMock,
):
    """
    GIVEN a valid performance request
    WHEN calculate_performance is called
    THEN it should orchestrate calls to repos and the engine correctly.
    """
    # ARRANGE
    request = PerformanceRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-02-15", "net_or_gross": "NET"},
            "periods": [{"type": "YTD"}],
            "options": {"include_attributes": True},
        }
    )

    with patch(
        "src.services.query_service.app.services.performance_service.PerformanceCalculator",
        new=mock_performance_calculator,
    ):
        # ACT
        response = await service.calculate_performance("P1", request)

        # ASSERT
        # 1. Verify Repositories were called
        mock_portfolio_repo.get_by_id.assert_called_once_with("P1")
        mock_performance_repo.get_portfolio_timeseries_for_range.assert_called_once()

        # 2. Verify the Engine was called
        mock_performance_calculator.assert_called_once()
        mock_performance_calculator.return_value.calculate_performance.assert_called_once()

        # 3. Verify the response is correctly assembled
        assert "YTD" in response.summary
        summary_result = response.summary["YTD"]
        assert summary_result.cumulative_return == 5.5
        assert summary_result.attributes is not None
        assert summary_result.attributes.begin_market_value == Decimal("1000")


async def test_calculate_performance_with_daily_breakdown(
    service: PerformanceService, mock_performance_calculator: MagicMock
):
    """
    GIVEN a performance request with a daily breakdown
    WHEN calculate_performance is called
    THEN the response should contain a correctly formatted breakdowns section.
    """
    # ARRANGE
    request = PerformanceRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-02-15", "net_or_gross": "NET"},
            "periods": [{"type": "YTD", "name": "YTD_With_Breakdown", "breakdown": "DAILY"}],
            "options": {"include_cumulative": True, "include_annualized": True},
        }
    )

    # Mock the engine to return a multi-day DataFrame
    mock_df = pd.DataFrame(
        [
            {
                "date": date(2025, 1, 1),
                "daily_ror_pct": Decimal("1.0"),
                "final_cumulative_ror_pct": Decimal("1.0"),
            },
            {
                "date": date(2025, 1, 2),
                "daily_ror_pct": Decimal("0.5"),
                "final_cumulative_ror_pct": Decimal("1.505"),
            },
        ]
    )
    mock_performance_calculator.return_value.calculate_performance.return_value = mock_df

    with patch(
        "src.services.query_service.app.services.performance_service.PerformanceCalculator",
        new=mock_performance_calculator,
    ):
        # ACT
        response = await service.calculate_performance("P1", request)

        # ASSERT
        assert response.breakdowns is not None
        assert "YTD_With_Breakdown" in response.breakdowns

        breakdown_result = response.breakdowns["YTD_With_Breakdown"]
        assert breakdown_result.breakdown_type == "DAILY"
        assert len(breakdown_result.results) == 2

        # Check the content of the first daily result
        day1_result = breakdown_result.results[0]
        assert day1_result.start_date == date(2025, 1, 1)
        assert day1_result.cumulative_return == 1.0
        assert (
            day1_result.annualized_return == 1.0
        )  # Annualized equals cumulative for short periods


async def test_calculate_performance_raises_for_missing_portfolio(
    service: PerformanceService, mock_portfolio_repo: AsyncMock
):
    """
    GIVEN a request for a non-existent portfolio
    WHEN calculate_performance is called
    THEN it should raise a ValueError.
    """
    # ARRANGE
    mock_portfolio_repo.get_by_id.return_value = None
    request = PerformanceRequest.model_validate(
        {"scope": {"as_of_date": "2025-01-01"}, "periods": [{"type": "YTD"}]}
    )

    # ACT & ASSERT
    with pytest.raises(ValueError, match="Portfolio P_NONEXISTENT not found"):
        await service.calculate_performance("P_NONEXISTENT", request)


def test_aggregate_attributes_empty_dataframe_returns_defaults(
    service: PerformanceService,
):
    result = service._aggregate_attributes(pd.DataFrame())
    assert result.begin_market_value is None
    assert result.end_market_value is None
    assert result.total_cashflow is None


async def test_calculate_performance_returns_empty_when_no_timeseries(
    service: PerformanceService, mock_performance_repo: AsyncMock
):
    request = PerformanceRequest.model_validate(
        {"scope": {"as_of_date": "2025-02-15", "net_or_gross": "NET"}, "periods": [{"type": "YTD"}]}
    )
    mock_performance_repo.get_portfolio_timeseries_for_range.return_value = []

    response = await service.calculate_performance("P1", request)

    assert response.summary == {}
    assert response.breakdowns is None


async def test_calculate_performance_period_without_data_returns_empty_result(
    service: PerformanceService, mock_performance_calculator: MagicMock
):
    request = PerformanceRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-02-15", "net_or_gross": "NET"},
            "periods": [
                {"type": "YTD"},
                {"type": "EXPLICIT", "name": "Future", "from": "2025-12-01", "to": "2025-12-31"},
            ],
        }
    )

    mock_df = pd.DataFrame(
        [
            {
                "date": date(2025, 1, 2),
                "daily_ror_pct": Decimal("1.0"),
                "final_cumulative_ror_pct": Decimal("1.0"),
            }
        ]
    )
    mock_performance_calculator.return_value.calculate_performance.return_value = mock_df

    with patch(
        "src.services.query_service.app.services.performance_service.PerformanceCalculator",
        new=mock_performance_calculator,
    ):
        response = await service.calculate_performance("P1", request)

    assert "Future" in response.summary
    assert response.summary["Future"].cumulative_return is None
    assert response.summary["Future"].annualized_return is None


async def test_calculate_performance_empty_engine_dataframe_returns_zero_cumulative(
    service: PerformanceService, mock_performance_calculator: MagicMock
):
    request = PerformanceRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-02-15", "net_or_gross": "NET"},
            "periods": [{"type": "YTD"}],
            "options": {"include_cumulative": True, "include_annualized": False},
        }
    )
    mock_performance_calculator.return_value.calculate_performance.return_value = pd.DataFrame()

    with patch(
        "src.services.query_service.app.services.performance_service.PerformanceCalculator",
        new=mock_performance_calculator,
    ):
        response = await service.calculate_performance("P1", request)

    assert response.summary["YTD"].cumulative_return == 0.0


async def test_calculate_breakdowns_weekly_path_returns_weekly_return(
    service: PerformanceService,
):
    request = PerformanceRequest.model_validate(
        {
            "scope": {"as_of_date": "2025-02-15", "net_or_gross": "NET"},
            "periods": [{"type": "YTD"}],
            "options": {
                "include_cumulative": True,
                "include_annualized": True,
                "include_attributes": True,
            },
        }
    )
    portfolio = Portfolio(portfolio_id="P1", open_date=date(2020, 1, 1))
    results_df = pd.DataFrame(
        [
            {
                "date": date(2025, 1, 1),
                "daily_ror_pct": Decimal("1.0"),
                "final_cumulative_ror_pct": Decimal("1.0"),
                "bod_market_value": Decimal("100"),
                "eod_market_value": Decimal("101"),
                "bod_cashflow": Decimal("0"),
                "eod_cashflow": Decimal("0"),
                "fees": Decimal("0"),
            },
            {
                "date": date(2025, 1, 2),
                "daily_ror_pct": Decimal("1.0"),
                "final_cumulative_ror_pct": Decimal("2.01"),
                "bod_market_value": Decimal("101"),
                "eod_market_value": Decimal("103"),
                "bod_cashflow": Decimal("0"),
                "eod_cashflow": Decimal("0"),
                "fees": Decimal("0"),
            },
        ]
    )

    with patch(
        "src.services.query_service.app.services.performance_service.PerformanceCalculator"
    ) as mock_calculator:
        mock_calculator.return_value.calculate_performance.return_value = pd.DataFrame(
            [{"final_cumulative_ror_pct": Decimal("2.01")}]
        )
        breakdowns = service._calculate_breakdowns(results_df, "WEEKLY", request, portfolio)

    assert len(breakdowns) == 1
    assert breakdowns[0].weekly_return is not None
    assert breakdowns[0].attributes is not None


async def test_calculate_breakdowns_invalid_type_returns_empty(
    service: PerformanceService,
):
    request = PerformanceRequest.model_validate(
        {"scope": {"as_of_date": "2025-02-15", "net_or_gross": "NET"}, "periods": [{"type": "YTD"}]}
    )
    portfolio = Portfolio(portfolio_id="P1", open_date=date(2020, 1, 1))
    results_df = pd.DataFrame(
        [
            {
                "date": date(2025, 1, 1),
                "daily_ror_pct": Decimal("1.0"),
                "final_cumulative_ror_pct": Decimal("1.0"),
            }
        ]
    )

    breakdowns = service._calculate_breakdowns(results_df, "UNKNOWN", request, portfolio)

    assert breakdowns == []
