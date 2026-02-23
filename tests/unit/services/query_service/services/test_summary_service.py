# tests/unit/services/query_service/services/test_summary_service.py
import pytest
from unittest.mock import AsyncMock, patch
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from src.services.query_service.app.services.summary_service import SummaryService
from src.services.query_service.app.dtos.summary_dto import SummaryRequest
from portfolio_common.database_models import (
    Portfolio,
    DailyPositionSnapshot,
    Instrument,
    Cashflow,
    Transaction,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    """Mocks all repository dependencies for the SummaryService."""
    mock_portfolio_repo = AsyncMock()
    mock_summary_repo = AsyncMock()

    mock_portfolio_repo.get_by_id.return_value = Portfolio(
        portfolio_id="P1",
        open_date=date(2023, 1, 1),
        base_currency="USD",
        risk_exposure="High",
        investment_time_horizon="Long",
        portfolio_type="Discretionary",
        booking_center="SG",
        cif_id="CIF_TEST",
        status="ACTIVE",
    )

    mock_snapshot_1 = DailyPositionSnapshot(security_id="S1", market_value=Decimal("50000"))
    mock_instrument_1 = Instrument(
        security_id="S1", product_type="Equity", asset_class="Equity", sector="Technology"
    )
    mock_snapshot_2 = DailyPositionSnapshot(security_id="S2", market_value=Decimal("30000"))
    mock_instrument_2 = Instrument(
        security_id="S2", product_type="Bond", asset_class="Fixed Income", sector=None
    )
    mock_snapshot_3 = DailyPositionSnapshot(security_id="S3", market_value=Decimal("20000"))
    mock_instrument_3 = Instrument(security_id="S3", product_type="Cash", asset_class="Cash")

    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (mock_snapshot_1, mock_instrument_1),
        (mock_snapshot_2, mock_instrument_2),
        (mock_snapshot_3, mock_instrument_3),
    ]

    mock_summary_repo.get_cashflows_for_period.return_value = [
        Cashflow(
            classification="CASHFLOW_IN",
            amount=Decimal("10000"),
            transaction=Transaction(transaction_type="DEPOSIT"),
        ),
        Cashflow(
            classification="CASHFLOW_OUT",
            amount=Decimal("-2000"),
            transaction=Transaction(transaction_type="WITHDRAWAL"),
        ),
        Cashflow(
            classification="TRANSFER",
            amount=Decimal("50000"),
            transaction=Transaction(transaction_type="TRANSFER_IN"),
        ),
        Cashflow(
            classification="TRANSFER",
            amount=Decimal("-15000"),
            transaction=Transaction(transaction_type="TRANSFER_OUT"),
        ),
        Cashflow(
            classification="INCOME",
            amount=Decimal("500"),
            transaction=Transaction(transaction_type="DIVIDEND"),
        ),
        Cashflow(
            classification="INCOME",
            amount=Decimal("150"),
            transaction=Transaction(transaction_type="INTEREST"),
        ),
        Cashflow(
            classification="EXPENSE",
            amount=Decimal("-100"),
            transaction=Transaction(transaction_type="FEE"),
        ),
    ]
    mock_summary_repo.get_realized_pnl.return_value = Decimal("1500")
    mock_summary_repo.get_total_unrealized_pnl.return_value = Decimal("0")

    with (
        patch(
            "src.services.query_service.app.services.summary_service.PortfolioRepository",
            return_value=mock_portfolio_repo,
        ),
        patch(
            "src.services.query_service.app.services.summary_service.SummaryRepository",
            return_value=mock_summary_repo,
        ),
    ):
        service = SummaryService(AsyncMock(spec=AsyncSession))
        yield {"service": service, "summary_repo": mock_summary_repo}


async def test_summary_service_calculates_wealth(mock_dependencies):
    service = mock_dependencies["service"]
    request = SummaryRequest.model_validate(
        {"as_of_date": "2025-08-29", "period": {"type": "YTD"}, "sections": ["WEALTH"]}
    )
    response = await service.get_portfolio_summary("P1", request)
    assert response.wealth.total_market_value == Decimal("100000")
    assert response.wealth.total_cash == Decimal("20000")


async def test_summary_service_calculates_allocation(mock_dependencies):
    service = mock_dependencies["service"]
    request = SummaryRequest.model_validate(
        {
            "as_of_date": "2025-08-29",
            "period": {"type": "YTD"},
            "sections": ["ALLOCATION"],
            "allocation_dimensions": ["ASSET_CLASS", "SECTOR"],
        }
    )
    response = await service.get_portfolio_summary("P1", request)
    assert response.allocation.by_sector[1].market_value == Decimal("50000")
    assert response.allocation.by_sector[1].weight == pytest.approx(0.5)


async def test_summary_service_calculates_all_sections(mock_dependencies):
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]
    mock_summary_repo.get_total_unrealized_pnl.side_effect = [Decimal("8000"), Decimal("10500")]
    request = SummaryRequest.model_validate(
        {
            "as_of_date": "2025-08-29",
            "period": {"type": "YTD"},
            "sections": ["WEALTH", "PNL", "INCOME", "ACTIVITY"],
        }
    )

    response = await service.get_portfolio_summary("P1", request)

    assert response.pnl_summary is not None
    assert response.income_summary is not None
    assert response.activity_summary is not None

    activity = response.activity_summary
    assert activity.total_deposits == Decimal("10000")
    assert activity.total_withdrawals == Decimal("-2000")
    assert activity.total_transfers_in == Decimal("50000")
    assert activity.total_transfers_out == Decimal("-15000")
    assert activity.total_fees == Decimal("-100")

    pnl = response.pnl_summary
    assert pnl.net_new_money == Decimal("43000")
    assert pnl.realized_pnl == Decimal("1500")
    assert pnl.unrealized_pnl_change == Decimal("2500")
    assert pnl.total_pnl == Decimal("4000")

    income = response.income_summary
    assert income.total_dividends == Decimal("500")
    assert income.total_interest == Decimal("150")


async def test_summary_service_calculates_maturity_bucket_from_as_of_date(mock_dependencies):
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]

    historical_as_of_date = date(2024, 8, 30)
    maturity_date = date(2025, 12, 31)

    mock_snapshot = DailyPositionSnapshot(security_id="BOND_1", market_value=Decimal("1000"))
    mock_instrument = Instrument(
        security_id="BOND_1",
        product_type="Bond",
        asset_class="Fixed Income",
        maturity_date=maturity_date,
    )
    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (mock_snapshot, mock_instrument)
    ]

    request = SummaryRequest.model_validate(
        {
            "as_of_date": historical_as_of_date.isoformat(),
            "period": {"type": "YTD"},
            "sections": ["ALLOCATION"],
            "allocation_dimensions": ["MATURITY_BUCKET"],
        }
    )

    response = await service.get_portfolio_summary("P1", request)
    allocation = response.allocation
    assert allocation is not None
    assert allocation.by_maturity_bucket is not None
    assert len(allocation.by_maturity_bucket) == 1
    assert allocation.by_maturity_bucket[0].group == "1-3Y"


# --- NEW FAILING TEST (TDD) ---
@patch(
    "src.services.query_service.app.services.summary_service.UNCLASSIFIED_ALLOCATION_MARKET_VALUE"
)
async def test_summary_service_sets_unclassified_metric(mock_gauge, mock_dependencies):
    """
    GIVEN a portfolio with an unclassified asset
    WHEN the summary service calculates allocation
    THEN it should set the Prometheus gauge with the value of the unclassified assets.
    """
    # ARRANGE
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]

    # Mock data with one unclassified instrument (asset_class is None)
    mock_snapshot = DailyPositionSnapshot(security_id="UNCLASS_1", market_value=Decimal("12345.67"))
    mock_instrument = Instrument(security_id="UNCLASS_1", product_type="Other", asset_class=None)
    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (mock_snapshot, mock_instrument)
    ]

    request = SummaryRequest.model_validate(
        {
            "as_of_date": "2025-08-29",
            "period": {"type": "YTD"},
            "sections": ["ALLOCATION"],
            "allocation_dimensions": ["ASSET_CLASS"],
        }
    )

    # ACT
    await service.get_portfolio_summary("P1", request)

    # ASSERT
    # Verify that the gauge's .set() method was called with the correct value
    mock_gauge.labels.assert_called_once_with(portfolio_id="P1", dimension="ASSET_CLASS")
    mock_gauge.labels.return_value.set.assert_called_once_with(12345.67)


async def test_summary_service_raises_when_portfolio_not_found(mock_dependencies):
    service = mock_dependencies["service"]
    service.portfolio_repo.get_by_id.return_value = None
    request = SummaryRequest.model_validate(
        {"as_of_date": "2025-08-29", "period": {"type": "YTD"}, "sections": ["WEALTH"]}
    )

    with pytest.raises(ValueError, match="Portfolio P404 not found"):
        await service.get_portfolio_summary("P404", request)


async def test_summary_service_skips_allocation_for_zero_market_value(mock_dependencies):
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]
    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (
            DailyPositionSnapshot(security_id="S_ZERO", market_value=Decimal("0")),
            Instrument(security_id="S_ZERO", product_type="Cash", asset_class=None),
        )
    ]
    request = SummaryRequest.model_validate(
        {
            "as_of_date": "2025-08-29",
            "period": {"type": "YTD"},
            "sections": ["ALLOCATION"],
            "allocation_dimensions": ["ASSET_CLASS"],
        }
    )

    response = await service.get_portfolio_summary("P1", request)

    assert response.allocation is not None
    assert response.allocation.by_asset_class == []


async def test_summary_service_uses_na_for_non_fixed_income_maturity_bucket(mock_dependencies):
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]
    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (
            DailyPositionSnapshot(security_id="EQ_1", market_value=Decimal("2500")),
            Instrument(
                security_id="EQ_1",
                product_type="Equity",
                asset_class="Equity",
                maturity_date=date(2030, 1, 1),
            ),
        )
    ]
    request = SummaryRequest.model_validate(
        {
            "as_of_date": "2025-08-29",
            "period": {"type": "YTD"},
            "sections": ["ALLOCATION"],
            "allocation_dimensions": ["MATURITY_BUCKET"],
        }
    )

    response = await service.get_portfolio_summary("P1", request)

    assert response.allocation is not None
    assert response.allocation.by_maturity_bucket is not None
    assert response.allocation.by_maturity_bucket[0].group == "N/A"


async def test_summary_service_allocation_section_without_dimensions_returns_none(
    mock_dependencies,
):
    service = mock_dependencies["service"]
    request = SummaryRequest.model_validate(
        {
            "as_of_date": "2025-08-29",
            "period": {"type": "YTD"},
            "sections": ["ALLOCATION"],
        }
    )

    response = await service.get_portfolio_summary("P1", request)

    assert response.allocation is None


async def test_summary_service_calculates_additional_maturity_buckets(mock_dependencies):
    service = mock_dependencies["service"]
    mock_summary_repo = mock_dependencies["summary_repo"]
    as_of_date = date(2025, 1, 1)

    mock_summary_repo.get_wealth_and_allocation_data.return_value = [
        (
            DailyPositionSnapshot(security_id="B1", market_value=Decimal("100")),
            Instrument(
                security_id="B1",
                product_type="Bond",
                asset_class="Fixed Income",
                maturity_date=date(2025, 10, 1),  # <= 1 year
            ),
        ),
        (
            DailyPositionSnapshot(security_id="B2", market_value=Decimal("100")),
            Instrument(
                security_id="B2",
                product_type="Bond",
                asset_class="Fixed Income",
                maturity_date=date(2029, 1, 1),  # <= 5 years
            ),
        ),
        (
            DailyPositionSnapshot(security_id="B3", market_value=Decimal("100")),
            Instrument(
                security_id="B3",
                product_type="Bond",
                asset_class="Fixed Income",
                maturity_date=date(2032, 1, 1),  # <= 10 years
            ),
        ),
        (
            DailyPositionSnapshot(security_id="B4", market_value=Decimal("100")),
            Instrument(
                security_id="B4",
                product_type="Bond",
                asset_class="Fixed Income",
                maturity_date=date(2040, 1, 1),  # > 10 years
            ),
        ),
    ]

    request = SummaryRequest.model_validate(
        {
            "as_of_date": as_of_date.isoformat(),
            "period": {"type": "YTD"},
            "sections": ["ALLOCATION"],
            "allocation_dimensions": ["MATURITY_BUCKET"],
        }
    )
    response = await service.get_portfolio_summary("P1", request)

    groups = [g.group for g in (response.allocation.by_maturity_bucket or [])]
    assert "0-1Y" in groups
    assert "3-5Y" in groups
    assert "5-10Y" in groups
    assert "10Y+" in groups
