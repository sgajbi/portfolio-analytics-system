import pytest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src.services.query_service.app.services.simulation_service import SimulationService
from src.services.query_service.app.dtos.simulation_dto import SimulationSessionCreateRequest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dependencies():
    repo = AsyncMock()
    position_repo = AsyncMock()
    instrument_repo = AsyncMock()

    session = SimpleNamespace(
        session_id="S1",
        portfolio_id="P1",
        status="ACTIVE",
        version=2,
        created_by="tester",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
    )
    repo.get_session.return_value = session
    repo.get_changes.return_value = [
        SimpleNamespace(
            change_id="C1",
            session_id="S1",
            portfolio_id="P1",
            security_id="SEC_AAPL_US",
            transaction_type="BUY",
            quantity=10,
            amount=None,
            price=None,
            currency="USD",
            effective_date=None,
            change_metadata={"source": "test"},
            created_at=datetime.now(timezone.utc),
        )
    ]

    position_repo.get_latest_positions_by_portfolio.return_value = []
    position_repo.get_latest_position_history_by_portfolio.return_value = [
        (
            SimpleNamespace(
                security_id="SEC_AAPL_US",
                quantity=100,
                cost_basis=1000,
                cost_basis_local=1000,
                position_date=datetime(2025, 9, 10).date(),
            ),
            SimpleNamespace(name="Apple", asset_class="Equity"),
            SimpleNamespace(status="CURRENT"),
        )
    ]
    instrument_repo.get_by_security_ids.return_value = [
        SimpleNamespace(security_id="SEC_AAPL_US", name="Apple", asset_class="Equity")
    ]

    with (
        patch(
            "src.services.query_service.app.services.simulation_service.SimulationRepository",
            return_value=repo,
        ),
        patch(
            "src.services.query_service.app.services.simulation_service.PositionRepository",
            return_value=position_repo,
        ),
        patch(
            "src.services.query_service.app.services.simulation_service.InstrumentRepository",
            return_value=instrument_repo,
        ),
    ):
        yield repo, position_repo, instrument_repo


async def test_create_session_returns_session_response(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.create_session.return_value = repo.get_session.return_value

    service = SimulationService(AsyncMock())
    request = SimulationSessionCreateRequest(portfolio_id="P1", created_by="tester", ttl_hours=24)
    response = await service.create_session(request)

    repo.create_session.assert_awaited_once_with(
        portfolio_id="P1", created_by="tester", ttl_hours=24
    )
    assert response.session.session_id == "S1"


async def test_projected_positions_applies_change_delta(mock_dependencies):
    _, _, _ = mock_dependencies
    service = SimulationService(AsyncMock())

    response = await service.get_projected_positions("S1")

    assert response.session_id == "S1"
    assert len(response.positions) == 1
    assert response.positions[0].baseline_quantity == 100.0
    assert response.positions[0].proposed_quantity == 110.0
    assert response.positions[0].delta_quantity == 10.0


async def test_delete_change_returns_updated_changes(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.delete_change.return_value = True

    service = SimulationService(AsyncMock())
    response = await service.delete_change("S1", "C1")

    assert response.session_id == "S1"
    assert response.version == 2
    assert len(response.changes) == 1
