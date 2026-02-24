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


async def test_get_session_raises_when_not_found(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.get_session.return_value = None
    service = SimulationService(AsyncMock())

    with pytest.raises(ValueError, match="not found"):
        await service.get_session("S404")


async def test_close_session_raises_when_not_found(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.get_session.return_value = None
    service = SimulationService(AsyncMock())

    with pytest.raises(ValueError, match="not found"):
        await service.close_session("S404")


async def test_add_changes_raises_when_session_inactive(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.get_session.return_value.status = "CLOSED"
    service = SimulationService(AsyncMock())

    with pytest.raises(ValueError, match="not active"):
        await service.add_changes("S1", [{"security_id": "SEC_AAPL_US", "transaction_type": "BUY"}])


async def test_add_changes_raises_when_session_expired(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.get_session.return_value.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    service = SimulationService(AsyncMock())

    with pytest.raises(ValueError, match="expired"):
        await service.add_changes("S1", [{"security_id": "SEC_AAPL_US", "transaction_type": "BUY"}])


async def test_delete_change_raises_when_change_missing(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.delete_change.return_value = False
    service = SimulationService(AsyncMock())

    with pytest.raises(ValueError, match="not found"):
        await service.delete_change("S1", "C404")


async def test_projected_positions_raises_when_session_missing(mock_dependencies):
    repo, _, _ = mock_dependencies
    repo.get_session.return_value = None
    service = SimulationService(AsyncMock())

    with pytest.raises(ValueError, match="not found"):
        await service.get_projected_positions("S404")


async def test_projected_positions_uses_snapshot_when_available(mock_dependencies):
    repo, position_repo, instrument_repo = mock_dependencies
    position_repo.get_latest_positions_by_portfolio.return_value = [
        (
            SimpleNamespace(
                security_id="SEC_MSFT_US",
                quantity=50,
                cost_basis=500,
                cost_basis_local=500,
                date=datetime(2025, 9, 11).date(),
            ),
            SimpleNamespace(name="Microsoft", asset_class="Equity"),
            SimpleNamespace(status="CURRENT"),
        )
    ]
    position_repo.get_latest_position_history_by_portfolio.return_value = []
    repo.get_changes.return_value = []
    instrument_repo.get_by_security_ids.return_value = []

    service = SimulationService(AsyncMock())
    response = await service.get_projected_positions("S1")

    assert response.baseline_as_of == datetime(2025, 9, 11).date()
    assert len(response.positions) == 1
    assert response.positions[0].security_id == "SEC_MSFT_US"


async def test_projected_positions_adds_new_security_from_change(mock_dependencies):
    repo, position_repo, instrument_repo = mock_dependencies
    position_repo.get_latest_positions_by_portfolio.return_value = []
    position_repo.get_latest_position_history_by_portfolio.return_value = []
    repo.get_changes.return_value = [
        SimpleNamespace(
            change_id="C2",
            session_id="S1",
            portfolio_id="P1",
            security_id="SEC_NEW_US",
            transaction_type="BUY",
            quantity=5,
            amount=None,
            price=None,
            currency="USD",
            effective_date=None,
            change_metadata=None,
            created_at=datetime.now(timezone.utc),
        )
    ]
    instrument_repo.get_by_security_ids.return_value = [
        SimpleNamespace(security_id="SEC_NEW_US", name="New Security", asset_class="Alternatives")
    ]

    service = SimulationService(AsyncMock())
    response = await service.get_projected_positions("S1")

    assert len(response.positions) == 1
    assert response.positions[0].security_id == "SEC_NEW_US"
    assert response.positions[0].instrument_name == "New Security"
    assert response.positions[0].delta_quantity == 5.0


async def test_projected_positions_filters_non_positive_after_changes(mock_dependencies):
    repo, _, instrument_repo = mock_dependencies
    repo.get_changes.return_value = [
        SimpleNamespace(
            change_id="C3",
            session_id="S1",
            portfolio_id="P1",
            security_id="SEC_AAPL_US",
            transaction_type="SELL",
            quantity=1000,
            amount=None,
            price=None,
            currency="USD",
            effective_date=None,
            change_metadata=None,
            created_at=datetime.now(timezone.utc),
        )
    ]
    instrument_repo.get_by_security_ids.return_value = []

    service = SimulationService(AsyncMock())
    response = await service.get_projected_positions("S1")

    assert response.positions == []


@pytest.mark.parametrize(
    ("transaction_type", "quantity", "amount", "expected"),
    [
        ("BUY", 10, None, 10.0),
        ("TRANSFER_IN", None, 5, 5.0),
        ("SELL", 7, None, -7.0),
        ("WITHDRAWAL", None, 3, -3.0),
        ("UNKNOWN", 9, None, 0.0),
    ],
)
async def test_change_quantity_effect_rules(transaction_type, quantity, amount, expected):
    change = SimpleNamespace(transaction_type=transaction_type, quantity=quantity, amount=amount)
    assert SimulationService._change_quantity_effect(change) == expected
