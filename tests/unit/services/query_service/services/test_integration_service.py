from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.query_service.app.dtos.integration_dto import (
    PortfolioCoreSnapshotRequest,
    PortfolioPerformanceInputRequest,
)
from src.services.query_service.app.services.integration_service import IntegrationService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_portfolio_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_review_service() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_performance_repository() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_portfolio_service: AsyncMock,
    mock_review_service: AsyncMock,
    mock_performance_repository: AsyncMock,
) -> IntegrationService:
    with (
        patch(
            "src.services.query_service.app.services.integration_service.PortfolioService",
            return_value=mock_portfolio_service,
        ),
        patch(
            "src.services.query_service.app.services.integration_service.ReviewService",
            return_value=mock_review_service,
        ),
        patch(
            "src.services.query_service.app.services.integration_service.PerformanceRepository",
            return_value=mock_performance_repository,
        ),
    ):
        return IntegrationService(AsyncMock(spec=AsyncSession))


async def test_get_portfolio_core_snapshot(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    mock_review_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", raising=False)
    monkeypatch.delenv("PAS_DEFAULT_TENANT_ID", raising=False)
    monkeypatch.setenv("PAS_INTEGRATION_MAX_STALENESS_DAYS", "10")

    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
        "close_date": None,
        "risk_exposure": "MODERATE",
        "investment_time_horizon": "LONG_TERM",
        "portfolio_type": "DISCRETIONARY",
        "objective": "GROWTH",
        "booking_center": "LON-01",
        "cif_id": "CIF-1",
        "is_leverage_allowed": False,
        "advisor_id": "ADV-1",
        "status": "ACTIVE",
    }
    mock_review_service.get_portfolio_review.return_value = {
        "portfolio_id": "P1",
        "as_of_date": date(2026, 2, 23),
        "overview": None,
        "allocation": None,
        "performance": None,
        "riskAnalytics": None,
        "incomeAndActivity": None,
        "holdings": None,
        "transactions": None,
    }

    request = PortfolioCoreSnapshotRequest.model_validate(
        {
            "asOfDate": "2026-02-23",
            "consumerSystem": "lotus-performance",
            "includeSections": ["OVERVIEW", "HOLDINGS"],
        }
    )

    response = await service.get_portfolio_core_snapshot("P1", request)

    assert response.consumer_system == "lotus-performance"
    assert response.contract_version == "v1"
    assert response.portfolio.portfolio_id == "P1"
    assert response.snapshot.portfolio_id == "P1"
    assert response.metadata.source_as_of_date == date(2026, 2, 23)
    assert response.metadata.freshness_status in {"FRESH", "STALE", "UNKNOWN"}
    assert response.metadata.lineage_refs.portfolio_id == "P1"
    assert response.metadata.section_governance.requested_sections == ["OVERVIEW", "HOLDINGS"]
    assert response.metadata.section_governance.effective_sections == ["OVERVIEW", "HOLDINGS"]
    assert response.metadata.section_governance.dropped_sections == []
    assert response.metadata.policy_provenance.policy_source in {"default", "global", "tenant"}
    assert response.metadata.policy_provenance.matched_rule_id
    assert isinstance(response.metadata.generated_at, datetime)
    assert response.metadata.generated_at.tzinfo == UTC

    mock_review_service.get_portfolio_review.assert_awaited_once()
    review_request = mock_review_service.get_portfolio_review.await_args.args[1]
    assert review_request.sections == ["OVERVIEW", "HOLDINGS"]


async def test_get_portfolio_core_snapshot_applies_policy_filter(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    mock_review_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
        "close_date": None,
        "risk_exposure": "MODERATE",
        "investment_time_horizon": "LONG_TERM",
        "portfolio_type": "DISCRETIONARY",
        "objective": "GROWTH",
        "booking_center": "LON-01",
        "cif_id": "CIF-1",
        "is_leverage_allowed": False,
        "advisor_id": "ADV-1",
        "status": "ACTIVE",
    }
    mock_review_service.get_portfolio_review.return_value = {
        "portfolio_id": "P1",
        "as_of_date": date(2026, 2, 23),
        "overview": None,
        "allocation": None,
        "performance": None,
        "riskAnalytics": None,
        "incomeAndActivity": None,
        "holdings": None,
        "transactions": None,
    }
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-performance":["OVERVIEW"]},"strictMode":false}',
    )

    request = PortfolioCoreSnapshotRequest.model_validate(
        {
            "asOfDate": "2026-02-23",
            "consumerSystem": "lotus-performance",
            "includeSections": ["OVERVIEW", "HOLDINGS", "PERFORMANCE"],
        }
    )

    response = await service.get_portfolio_core_snapshot("P1", request)
    assert response.metadata.section_governance.effective_sections == ["OVERVIEW"]
    assert response.metadata.section_governance.dropped_sections == ["HOLDINGS", "PERFORMANCE"]
    assert response.metadata.section_governance.warnings == ["SECTIONS_FILTERED_BY_POLICY"]


async def test_get_portfolio_core_snapshot_rejects_disallowed_sections_in_strict_mode(
    service: IntegrationService,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-performance":["OVERVIEW"]},"strictMode":true}',
    )
    request = PortfolioCoreSnapshotRequest.model_validate(
        {
            "asOfDate": "2026-02-23",
            "consumerSystem": "lotus-performance",
            "includeSections": ["OVERVIEW", "HOLDINGS"],
        }
    )

    with pytest.raises(PermissionError):
        await service.get_portfolio_core_snapshot("P1", request)


async def test_get_portfolio_core_snapshot_rejects_pa_owned_analytics_sections_in_strict_mode(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
    }
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-performance":["OVERVIEW","RISK_ANALYTICS"]},"strictMode":true}',
    )

    request = PortfolioCoreSnapshotRequest.model_validate(
        {
            "asOfDate": "2026-02-23",
            "consumerSystem": "lotus-performance",
            "includeSections": ["OVERVIEW", "RISK_ANALYTICS"],
        }
    )

    with pytest.raises(PermissionError, match="not owned by lotus-core core snapshot contract"):
        await service.get_portfolio_core_snapshot("P1", request)


async def test_get_portfolio_performance_input(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    mock_performance_repository: AsyncMock,
):
    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
        "close_date": None,
        "risk_exposure": "MODERATE",
        "investment_time_horizon": "LONG_TERM",
        "portfolio_type": "DISCRETIONARY",
        "objective": "GROWTH",
        "booking_center": "LON-01",
        "cif_id": "CIF-1",
        "is_leverage_allowed": False,
        "advisor_id": "ADV-1",
        "status": "ACTIVE",
    }
    mock_performance_repository.get_portfolio_timeseries_for_range.return_value = [
        SimpleNamespace(
            date=date(2026, 2, 20),
            bod_market_value=100.0,
            bod_cashflow=0.0,
            eod_cashflow=0.0,
            fees=0.0,
            eod_market_value=101.0,
        ),
        SimpleNamespace(
            date=date(2026, 2, 21),
            bod_market_value=101.0,
            bod_cashflow=5.0,
            eod_cashflow=0.0,
            fees=0.1,
            eod_market_value=106.0,
        ),
    ]
    request = PortfolioPerformanceInputRequest.model_validate(
        {"asOfDate": "2026-02-21", "consumerSystem": "lotus-performance", "lookbackDays": 365}
    )

    response = await service.get_portfolio_performance_input("P1", request)
    assert response.portfolio_id == "P1"
    assert response.base_currency == "USD"
    assert response.performance_start_date == date(2026, 2, 20)
    assert len(response.valuation_points) == 2
    assert response.valuation_points[1].begin_mv == 101.0
    assert response.valuation_points[1].bod_cf == 5.0


async def test_get_portfolio_performance_input_rejects_when_rows_missing(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    mock_performance_repository: AsyncMock,
):
    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
    }
    mock_performance_repository.get_portfolio_timeseries_for_range.return_value = []
    request = PortfolioPerformanceInputRequest.model_validate(
        {"asOfDate": "2026-02-21", "consumerSystem": "lotus-performance", "lookbackDays": 365}
    )

    with pytest.raises(ValueError, match="No portfolio_timeseries rows found"):
        await service.get_portfolio_performance_input("P1", request)


async def test_get_portfolio_core_snapshot_future_as_of_sets_unknown_freshness(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    mock_review_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PAS_INTEGRATION_MAX_STALENESS_DAYS", "1")
    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
        "close_date": None,
        "risk_exposure": "MODERATE",
        "investment_time_horizon": "LONG_TERM",
        "portfolio_type": "DISCRETIONARY",
        "objective": "GROWTH",
        "booking_center": "LON-01",
        "cif_id": "CIF-1",
        "is_leverage_allowed": False,
        "advisor_id": "ADV-1",
        "status": "ACTIVE",
    }
    mock_review_service.get_portfolio_review.return_value = {
        "portfolio_id": "P1",
        "as_of_date": date(2027, 1, 1),
        "overview": None,
        "allocation": None,
        "performance": None,
        "riskAnalytics": None,
        "incomeAndActivity": None,
        "holdings": None,
        "transactions": None,
    }
    request = PortfolioCoreSnapshotRequest.model_validate(
        {
            "asOfDate": "2027-01-01",
            "consumerSystem": "lotus-performance",
            "includeSections": ["OVERVIEW"],
        }
    )

    response = await service.get_portfolio_core_snapshot("P1", request)
    assert response.metadata.freshness_status == "UNKNOWN"


def test_get_effective_policy_returns_context(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"strictMode":false,"consumers":{"lotus-performance":["OVERVIEW","HOLDINGS"]}}',
    )
    monkeypatch.setenv("PAS_POLICY_VERSION", "tenant-default-v2")

    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="default",
        include_sections=["OVERVIEW", "HOLDINGS", "TRANSACTIONS"],
    )

    assert response.consumer_system == "lotus-performance"
    assert response.policy_provenance.policy_version == "tenant-default-v2"
    assert response.policy_provenance.policy_source == "global"
    assert response.policy_provenance.strict_mode is False
    assert response.allowed_sections == ["OVERVIEW", "HOLDINGS"]
    assert "SECTIONS_FILTERED_BY_POLICY" in response.warnings


def test_get_effective_policy_with_tenant_override(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"strictMode":false,"consumers":{"lotus-performance":["OVERVIEW"]},'
            '"tenants":{"tenant-a":{"strictMode":true,"consumers":{"lotus-performance":["HOLDINGS"]}}}}'
        ),
    )

    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="tenant-a",
        include_sections=["HOLDINGS"],
    )

    assert response.policy_provenance.policy_source == "tenant"
    assert response.policy_provenance.strict_mode is True
    assert response.allowed_sections == ["HOLDINGS"]


def test_get_effective_policy_returns_warning_when_no_section_restriction(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", '{"strictMode":false}')
    response = service.get_effective_policy(
        consumer_system="pa",
        tenant_id="default",
        include_sections=None,
    )
    assert response.consumer_system == "lotus-performance"
    assert response.allowed_sections == []
    assert "NO_ALLOWED_SECTION_OVERRIDE" in response.warnings
    assert "NO_ALLOWED_SECTION_RESTRICTION" in response.warnings


def test_get_effective_policy_handles_invalid_json_policy(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", "{bad json")
    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="default",
        include_sections=["OVERVIEW"],
    )
    assert response.allowed_sections == ["OVERVIEW"]


def test_get_effective_policy_handles_non_dict_policy_payload(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PAS_INTEGRATION_SNAPSHOT_POLICY_JSON", '["not-a-dict"]')
    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="default",
        include_sections=["OVERVIEW"],
    )
    assert response.allowed_sections == ["OVERVIEW"]


def test_get_effective_policy_uses_tenant_default_sections_when_consumer_override_missing(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        (
            '{"strictMode":false,"tenants":{"tenant-b":{"consumers":{},'
            '"defaultSections":["overview","holdings"]}}}'
        ),
    )
    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="tenant-b",
        include_sections=["OVERVIEW", "HOLDINGS", "TRANSACTIONS"],
    )
    assert response.policy_provenance.matched_rule_id == "tenant.tenant-b.defaultSections"
    assert [str(item) for item in response.allowed_sections] == [
        "ReviewSection.OVERVIEW",
        "ReviewSection.HOLDINGS",
        "ReviewSection.TRANSACTIONS",
    ]


def test_get_effective_policy_uses_tenant_strictmode_rule_when_no_section_rules(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"tenants":{"tenant-c":{"strictMode":true}}}',
    )
    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="tenant-c",
        include_sections=None,
    )
    assert response.policy_provenance.matched_rule_id == "tenant.tenant-c.strictMode"
    assert response.policy_provenance.strict_mode is True


def test_get_effective_policy_returns_context_sections_when_include_sections_not_provided(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"strictMode":false,"consumers":{"lotus-performance":["OVERVIEW","HOLDINGS"]}}',
    )
    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="default",
        include_sections=None,
    )
    assert response.allowed_sections == ["OVERVIEW", "HOLDINGS"]
    assert response.warnings == []


def test_get_effective_policy_delegates_analytics_sections_to_pa_in_non_strict_mode(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"strictMode":false,"consumers":{"lotus-performance":["OVERVIEW","PERFORMANCE","RISK_ANALYTICS"]}}',
    )
    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="default",
        include_sections=["OVERVIEW", "PERFORMANCE", "RISK_ANALYTICS"],
    )
    assert response.allowed_sections == ["OVERVIEW"]
    assert "ANALYTICS_SECTIONS_DELEGATED_TO_PA" in response.warnings


def test_read_attr_or_key_supports_attr_dict_and_default():
    obj = SimpleNamespace(portfolio_id="P1")
    assert IntegrationService._read_attr_or_key(obj, "portfolio_id") == "P1"
    assert IntegrationService._read_attr_or_key({"portfolio_id": "P2"}, "portfolio_id") == "P2"
    assert IntegrationService._read_attr_or_key(123, "portfolio_id", "fallback") == "fallback"


def test_resolve_freshness_status_returns_stale_for_old_as_of_date(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PAS_INTEGRATION_MAX_STALENESS_DAYS", "1")
    stale_date = date.today() - timedelta(days=10)
    assert IntegrationService._resolve_freshness_status(stale_date) == "STALE"


def test_canonical_consumer_system_handles_blank_value():
    assert IntegrationService._canonical_consumer_system("   ") == "unknown"


async def test_get_portfolio_core_snapshot_raises_when_policy_filters_all_sections(
    service: IntegrationService,
    mock_portfolio_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
):
    mock_portfolio_service.get_portfolio_by_id.return_value = {
        "portfolio_id": "P1",
        "base_currency": "USD",
        "open_date": date(2025, 1, 1),
    }
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"consumers":{"lotus-performance":["ALLOCATION"]},"strictMode":false}',
    )
    request = PortfolioCoreSnapshotRequest.model_validate(
        {
            "asOfDate": "2026-02-23",
            "consumerSystem": "lotus-performance",
            "includeSections": ["OVERVIEW"],
        }
    )

    with pytest.raises(PermissionError, match="No includeSections are allowed"):
        await service.get_portfolio_core_snapshot("P1", request)


def test_get_effective_policy_sets_tenant_default_rule_marker(
    service: IntegrationService, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(
        "PAS_INTEGRATION_SNAPSHOT_POLICY_JSON",
        '{"tenants":{"tenant-z":{"defaultSections":[]}}}',
    )
    response = service.get_effective_policy(
        consumer_system="lotus-performance",
        tenant_id="tenant-z",
        include_sections=["OVERVIEW"],
    )
    assert response.policy_provenance.matched_rule_id == "tenant.tenant-z.defaultSections"
