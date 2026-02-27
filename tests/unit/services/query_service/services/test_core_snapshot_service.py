from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.query_service.app.dtos.core_snapshot_dto import (
    CoreSnapshotMode,
    CoreSnapshotRequest,
    CoreSnapshotSection,
)
from src.services.query_service.app.services.core_snapshot_service import (
    CoreSnapshotBadRequestError,
    CoreSnapshotConflictError,
    CoreSnapshotNotFoundError,
    CoreSnapshotService,
    CoreSnapshotUnavailableSectionError,
)

pytestmark = pytest.mark.asyncio


def _snapshot_row(
    security_id: str = "SEC_AAPL_US",
    quantity: Decimal = Decimal("10"),
    market_value: Decimal = Decimal("100"),
    market_value_local: Decimal = Decimal("100"),
):
    return SimpleNamespace(
        security_id=security_id,
        quantity=quantity,
        market_value=market_value,
        market_value_local=market_value_local,
    )


def _instrument(
    security_id: str = "SEC_AAPL_US",
    currency: str = "USD",
    asset_class: str = "EQUITY",
):
    return SimpleNamespace(
        security_id=security_id,
        name=f"{security_id}-name",
        isin=f"{security_id}-isin",
        currency=currency,
        asset_class=asset_class,
        sector="TECHNOLOGY",
        country_of_risk="US",
    )


@pytest.fixture
def mock_dependencies():
    position_repo = AsyncMock()
    portfolio_repo = AsyncMock()
    simulation_repo = AsyncMock()
    price_repo = AsyncMock()
    fx_repo = AsyncMock()
    instrument_repo = AsyncMock()

    portfolio_repo.get_by_id.return_value = SimpleNamespace(
        portfolio_id="PORT_001",
        base_currency="USD",
    )
    position_repo.get_latest_positions_by_portfolio_as_of_date.return_value = [
        (_snapshot_row(), _instrument(), SimpleNamespace(status="CURRENT"))
    ]
    position_repo.get_latest_position_history_by_portfolio_as_of_date.return_value = []
    simulation_repo.get_session.return_value = SimpleNamespace(
        session_id="SIM_1",
        portfolio_id="PORT_001",
        version=3,
    )
    simulation_repo.get_changes.return_value = []
    fx_repo.get_fx_rates.return_value = [SimpleNamespace(rate=Decimal("1.1"))]
    price_repo.get_prices.return_value = [SimpleNamespace(price=Decimal("10"), currency="USD")]
    instrument_repo.get_by_security_ids.return_value = [_instrument("SEC_NEW_US")]

    with (
        patch(
            "src.services.query_service.app.services.core_snapshot_service.PositionRepository",
            return_value=position_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.PortfolioRepository",
            return_value=portfolio_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.SimulationRepository",
            return_value=simulation_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.MarketPriceRepository",
            return_value=price_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.FxRateRepository",
            return_value=fx_repo,
        ),
        patch(
            "src.services.query_service.app.services.core_snapshot_service.InstrumentRepository",
            return_value=instrument_repo,
        ),
    ):
        yield (
            position_repo,
            portfolio_repo,
            simulation_repo,
            price_repo,
            fx_repo,
            instrument_repo,
        )


async def test_core_snapshot_baseline_success(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[
            CoreSnapshotSection.POSITIONS_BASELINE,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
            CoreSnapshotSection.INSTRUMENT_ENRICHMENT,
        ],
    )

    response = await service.get_core_snapshot("PORT_001", request)

    assert response.portfolio_id == "PORT_001"
    assert response.sections.positions_baseline is not None
    assert len(response.sections.positions_baseline) == 1
    assert response.sections.portfolio_totals is not None
    assert response.sections.instrument_enrichment is not None


async def test_core_snapshot_simulation_success(mock_dependencies):
    (_, _, simulation_repo, _, _, _) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_AAPL_US",
            transaction_type="BUY",
            quantity=Decimal("5"),
            amount=None,
        )
    ]
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[
            CoreSnapshotSection.POSITIONS_BASELINE,
            CoreSnapshotSection.POSITIONS_PROJECTED,
            CoreSnapshotSection.POSITIONS_DELTA,
            CoreSnapshotSection.PORTFOLIO_TOTALS,
        ],
        simulation={"session_id": "SIM_1", "expected_version": 3},
    )

    response = await service.get_core_snapshot("PORT_001", request)

    assert response.simulation is not None
    assert response.sections.positions_projected is not None
    assert response.sections.positions_delta is not None
    assert response.sections.positions_projected[0].quantity == Decimal("15")


async def test_core_snapshot_rejects_projected_sections_in_baseline_mode(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
    )

    with pytest.raises(CoreSnapshotBadRequestError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_portfolio_missing(mock_dependencies):
    (_, portfolio_repo, _, _, _, _) = mock_dependencies
    portfolio_repo.get_by_id.return_value = None
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )

    with pytest.raises(CoreSnapshotNotFoundError):
        await service.get_core_snapshot("PORT_404", request)


async def test_core_snapshot_raises_when_simulation_session_missing(mock_dependencies):
    (_, _, simulation_repo, _, _, _) = mock_dependencies
    simulation_repo.get_session.return_value = None
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_404"},
    )

    with pytest.raises(CoreSnapshotNotFoundError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_session_portfolio_mismatch(mock_dependencies):
    (_, _, simulation_repo, _, _, _) = mock_dependencies
    simulation_repo.get_session.return_value = SimpleNamespace(
        session_id="SIM_1",
        portfolio_id="PORT_X",
        version=3,
    )
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
    )

    with pytest.raises(CoreSnapshotConflictError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_expected_version_mismatch(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1", "expected_version": 99},
    )

    with pytest.raises(CoreSnapshotConflictError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_fx_rate_missing(mock_dependencies):
    (_, portfolio_repo, _, _, fx_repo, _) = mock_dependencies
    portfolio_repo.get_by_id.return_value = SimpleNamespace(
        portfolio_id="PORT_001",
        base_currency="EUR",
    )
    fx_repo.get_fx_rates.return_value = []
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.BASELINE,
        reporting_currency="USD",
        sections=[CoreSnapshotSection.POSITIONS_BASELINE],
    )

    with pytest.raises(CoreSnapshotUnavailableSectionError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_new_security_has_no_instrument(mock_dependencies):
    (_, _, simulation_repo, _, _, instrument_repo) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_UNKNOWN",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        )
    ]
    instrument_repo.get_by_security_ids.return_value = []
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
    )

    with pytest.raises(CoreSnapshotUnavailableSectionError):
        await service.get_core_snapshot("PORT_001", request)


async def test_core_snapshot_raises_when_new_security_has_no_market_price(mock_dependencies):
    (_, _, simulation_repo, price_repo, _, _) = mock_dependencies
    simulation_repo.get_changes.return_value = [
        SimpleNamespace(
            security_id="SEC_NEW_US",
            transaction_type="BUY",
            quantity=Decimal("2"),
            amount=None,
        )
    ]
    price_repo.get_prices.return_value = []
    service = CoreSnapshotService(AsyncMock())
    request = CoreSnapshotRequest(
        as_of_date="2026-02-27",
        snapshot_mode=CoreSnapshotMode.SIMULATION,
        sections=[CoreSnapshotSection.POSITIONS_PROJECTED],
        simulation={"session_id": "SIM_1"},
    )

    with pytest.raises(CoreSnapshotUnavailableSectionError):
        await service.get_core_snapshot("PORT_001", request)


@pytest.mark.parametrize(
    ("txn_type", "quantity", "amount", "expected"),
    [
        ("BUY", Decimal("2"), None, Decimal("2")),
        ("SELL", Decimal("2"), None, Decimal("-2")),
        ("DEPOSIT", None, Decimal("7"), Decimal("7")),
        ("WITHDRAWAL", None, Decimal("7"), Decimal("-7")),
        ("UNKNOWN", Decimal("3"), None, Decimal("0")),
    ],
)
async def test_change_quantity_effect_rules(txn_type, quantity, amount, expected):
    change = SimpleNamespace(transaction_type=txn_type, quantity=quantity, amount=amount)
    assert CoreSnapshotService._change_quantity_effect(change) == expected


async def test_get_fx_rate_or_raise_identity_currency(mock_dependencies):
    service = CoreSnapshotService(AsyncMock())
    rate = await service._get_fx_rate_or_raise("USD", "USD", date(2026, 2, 27))
    assert rate == Decimal("1")
