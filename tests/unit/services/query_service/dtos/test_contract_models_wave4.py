import pytest
from pydantic import ValidationError

from src.services.query_service.app.dtos.mwr_dto import MWRRequest
from src.services.query_service.app.dtos.performance_dto import PerformanceRequest
from src.services.query_service.app.dtos.position_analytics_dto import (
    EnrichedPosition,
    PositionAnalyticsRequest,
    PositionAnalyticsResponse,
    PositionAnalyticsSection,
    PositionInstrumentDetails,
    PositionPerformance,
    PositionValuation,
)
from src.services.query_service.app.dtos.review_dto import (
    PortfolioReviewRequest,
    PortfolioReviewResponse,
    ReviewSection,
)


@pytest.mark.parametrize("period_type", ["MTD", "QTD", "YTD", "THREE_YEAR", "FIVE_YEAR", "SI"])
def test_performance_request_accepts_standard_period_types(period_type: str):
    payload = {
        "scope": {"as_of_date": "2026-02-24", "net_or_gross": "NET"},
        "periods": [{"type": period_type}],
    }
    request = PerformanceRequest.model_validate(payload)
    assert request.periods[0].type == period_type


@pytest.mark.parametrize("year", [1899, 1900, 2100, 2101])
def test_performance_request_rejects_out_of_range_year(year: int):
    payload = {
        "scope": {"as_of_date": "2026-02-24", "net_or_gross": "NET"},
        "periods": [{"type": "YEAR", "year": year}],
    }
    with pytest.raises(ValidationError):
        PerformanceRequest.model_validate(payload)


@pytest.mark.parametrize(
    "period_payload",
    [
        {"type": "EXPLICIT", "to": "2026-01-31"},
        {"type": "EXPLICIT", "from": "2026-01-01"},
        {"type": "EXPLICIT", "from": "2026-01-01", "to": None},
        {"type": "EXPLICIT", "from": None, "to": "2026-01-31"},
    ],
)
def test_performance_request_requires_explicit_bounds(period_payload: dict):
    payload = {"scope": {"as_of_date": "2026-02-24"}, "periods": [period_payload]}
    with pytest.raises(ValidationError):
        PerformanceRequest.model_validate(payload)


@pytest.mark.parametrize("breakdown", ["YEARLY", "INTRADAY", ""])
def test_performance_request_rejects_invalid_breakdown(breakdown: str):
    payload = {
        "scope": {"as_of_date": "2026-02-24", "net_or_gross": "NET"},
        "periods": [{"type": "YTD", "breakdown": breakdown}],
    }
    with pytest.raises(ValidationError):
        PerformanceRequest.model_validate(payload)


@pytest.mark.parametrize("period_type", ["MTD", "QTD", "YTD", "SI"])
def test_mwr_request_accepts_standard_period_types(period_type: str):
    payload = {"scope": {"as_of_date": "2026-02-24"}, "periods": [{"type": period_type}]}
    request = MWRRequest.model_validate(payload)
    assert request.periods[0].type == period_type


@pytest.mark.parametrize(
    "explicit_payload",
    [
        {"type": "EXPLICIT", "from": "2026-01-01", "to": "2026-01-31"},
        {
            "type": "EXPLICIT",
            "name": "Jan-Window",
            "from": "2026-01-01",
            "to": "2026-01-31",
        },
    ],
)
def test_mwr_request_accepts_explicit_period_aliases(explicit_payload: dict):
    payload = {"scope": {"as_of_date": "2026-02-24"}, "periods": [explicit_payload]}
    request = MWRRequest.model_validate(payload)
    assert request.periods[0].type == "EXPLICIT"


@pytest.mark.parametrize(
    "invalid_payload",
    [
        {"type": "UNKNOWN"},
        {"type": "EXPLICIT", "from": "2026-01-01"},
        {"type": "EXPLICIT", "to": "2026-01-31"},
    ],
)
def test_mwr_request_rejects_invalid_period_payloads(invalid_payload: dict):
    with pytest.raises(ValidationError):
        MWRRequest.model_validate(
            {"scope": {"as_of_date": "2026-02-24"}, "periods": [invalid_payload]}
        )


@pytest.mark.parametrize("section", [item.value for item in ReviewSection])
def test_review_request_accepts_all_review_sections(section: str):
    request = PortfolioReviewRequest.model_validate(
        {"as_of_date": "2026-02-24", "sections": [section]}
    )
    assert request.sections[0].value == section


@pytest.mark.parametrize("section", ["overview", "performance", "risk", "BASE"])
def test_review_request_rejects_invalid_review_sections(section: str):
    with pytest.raises(ValidationError):
        PortfolioReviewRequest.model_validate({"as_of_date": "2026-02-24", "sections": [section]})


@pytest.mark.parametrize(
    "risk_key,income_key",
    [
        ("riskAnalytics", "incomeAndActivity"),
        ("risk_analytics", "income_and_activity"),
    ],
)
def test_review_response_accepts_alias_and_field_names(risk_key: str, income_key: str):
    payload = {
        "portfolio_id": "P1",
        "as_of_date": "2026-02-24",
        risk_key: {
            "scope": {"as_of_date": "2026-02-24", "net_or_gross": "NET"},
            "results": {
                "YTD": {
                    "start_date": "2026-01-01",
                    "end_date": "2026-02-24",
                    "metrics": {"VOLATILITY": {"value": 0.1}},
                }
            },
        },
        income_key: {"income_summary_ytd": {}, "activity_summary_ytd": {}},
    }
    response = PortfolioReviewResponse.model_validate(payload)
    assert response.risk_analytics is not None
    assert response.income_and_activity is not None


@pytest.mark.parametrize(
    "section",
    [item.value for item in PositionAnalyticsSection],
)
def test_position_analytics_request_accepts_each_section(section: str):
    request = PositionAnalyticsRequest.model_validate(
        {"asOfDate": "2026-02-24", "sections": [section]}
    )
    assert request.sections[0].value == section


@pytest.mark.parametrize(
    "section_list",
    [
        ["BASE", "VALUATION"],
        ["BASE", "INCOME", "PERFORMANCE"],
        ["INSTRUMENT_DETAILS", "VALUATION", "PERFORMANCE"],
        ["BASE", "INSTRUMENT_DETAILS", "VALUATION", "INCOME", "PERFORMANCE"],
    ],
)
def test_position_analytics_request_accepts_section_combinations(section_list: list[str]):
    request = PositionAnalyticsRequest.model_validate(
        {"asOfDate": "2026-02-24", "sections": section_list}
    )
    assert [item.value for item in request.sections] == section_list


@pytest.mark.parametrize("period", ["MTD", "QTD", "YTD", "ONE_YEAR", "SI"])
def test_position_analytics_request_accepts_performance_period_literals(period: str):
    request = PositionAnalyticsRequest.model_validate(
        {
            "asOfDate": "2026-02-24",
            "sections": ["BASE", "PERFORMANCE"],
            "performanceOptions": {"periods": [period]},
        }
    )
    assert request.performance_options is not None
    assert request.performance_options.periods == [period]


@pytest.mark.parametrize("period", ["TEN_YEAR", "DAILY", "CUSTOM"])
def test_position_analytics_request_rejects_invalid_performance_literals(period: str):
    with pytest.raises(ValidationError):
        PositionAnalyticsRequest.model_validate(
            {
                "asOfDate": "2026-02-24",
                "sections": ["BASE", "PERFORMANCE"],
                "performanceOptions": {"periods": [period]},
            }
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "A", "isin": "X", "currency": "USD", "assetClass": "Equity"},
        {"name": "B", "isin": "Y", "currency": "USD", "countryOfRisk": "US"},
    ],
)
def test_position_instrument_details_supports_alias_fields(payload: dict):
    dto = PositionInstrumentDetails.model_validate(payload)
    assert dto.currency == "USD"


def test_position_valuation_supports_alias_payload():
    valuation = PositionValuation.model_validate(
        {
            "marketValue": {
                "local": {"amount": 100.0, "currency": "USD"},
                "base": {"amount": 100.0, "currency": "USD"},
            },
            "costBasis": {
                "local": {"amount": 90.0, "currency": "USD"},
                "base": {"amount": 90.0, "currency": "USD"},
            },
            "unrealizedPnl": {
                "local": {"amount": 10.0, "currency": "USD"},
                "base": {"amount": 10.0, "currency": "USD"},
            },
        }
    )
    assert valuation.market_value.local.amount == 100.0
    assert valuation.unrealized_pnl.base.amount == 10.0


@pytest.mark.parametrize(
    "performance_key",
    ["YTD", "MTD", "SI", "QTD"],
)
def test_enriched_position_accepts_performance_map(performance_key: str):
    enriched = EnrichedPosition.model_validate(
        {
            "securityId": "SEC_1",
            "quantity": 10.0,
            "weight": 0.2,
            "heldSinceDate": "2025-01-01",
            "performance": {
                performance_key: PositionPerformance(localReturn=1.2, baseReturn=1.0).model_dump(
                    by_alias=True
                )
            },
        }
    )
    assert performance_key in enriched.performance


@pytest.mark.parametrize(
    "total_mv",
    [0.0, 100.0, 999.99, 1000000.0],
)
def test_position_analytics_response_serializes_aliases(total_mv: float):
    response = PositionAnalyticsResponse.model_validate(
        {
            "portfolioId": "P1",
            "asOfDate": "2026-02-24",
            "totalMarketValue": total_mv,
            "positions": [],
        }
    )
    dumped = response.model_dump(by_alias=True)
    assert "portfolioId" in dumped
    assert "totalMarketValue" in dumped
