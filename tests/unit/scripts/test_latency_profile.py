from unittest.mock import MagicMock

from scripts.latency_profile import (
    _enforce_gate,
    _percentile_ms,
    _pick_identifier_from_payload,
    _resolve_runtime_ids,
)


def test_percentile_single_sample() -> None:
    assert _percentile_ms([12.5], 95) == 12.5


def test_enforce_gate_detects_budget_and_status_violations() -> None:
    passed, violations = _enforce_gate(
        [
            {
                "name": "ok_case",
                "runs": 10,
                "ok_runs": 10,
                "p95_ms": 99.0,
                "p95_budget_ms": 100.0,
            },
            {
                "name": "status_fail_case",
                "runs": 10,
                "ok_runs": 9,
                "p95_ms": 50.0,
                "p95_budget_ms": 100.0,
            },
            {
                "name": "budget_fail_case",
                "runs": 10,
                "ok_runs": 10,
                "p95_ms": 120.0,
                "p95_budget_ms": 100.0,
            },
        ]
    )
    assert not passed
    assert any("status_fail_case" in v for v in violations)
    assert any("budget_fail_case" in v for v in violations)


def test_pick_identifier_from_payload_nested() -> None:
    payload = {
        "data": {
            "items": [
                {"portfolio_id": "PORT_001"},
            ]
        }
    }
    assert _pick_identifier_from_payload(payload, ("portfolio_id",)) == "PORT_001"


def test_resolve_runtime_ids_overrides_from_catalogs() -> None:
    session = MagicMock()
    portfolio_response = MagicMock()
    portfolio_response.status_code = 200
    portfolio_response.json.return_value = {"items": [{"portfolio_id": "PORT_123"}]}
    benchmark_response = MagicMock()
    benchmark_response.status_code = 200
    benchmark_response.json.return_value = {"benchmarks": [{"benchmark_id": "BMK_ABC"}]}
    session.get.return_value = portfolio_response
    session.post.return_value = benchmark_response

    portfolio_id, benchmark_id = _resolve_runtime_ids(
        session,
        query_base_url="http://localhost:8201",
        portfolio_id="DEMO_DPM_EUR_001",
        benchmark_id="BMK_GLOBAL_BALANCED_60_40",
    )

    assert portfolio_id == "PORT_123"
    assert benchmark_id == "BMK_ABC"
