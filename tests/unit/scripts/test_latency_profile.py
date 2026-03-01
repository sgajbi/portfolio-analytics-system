from scripts.latency_profile import _enforce_gate, _percentile_ms


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
