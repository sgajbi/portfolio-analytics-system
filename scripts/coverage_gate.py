"""Run stable query-service suites with coverage and enforce a threshold."""

from __future__ import annotations

import os
import subprocess
import sys


UNIT_ARGS = ["tests/unit/services/query_service"]
INTEGRATION_LITE_ARGS = [
    "tests/integration/services/query_service/test_concentration_router.py",
    "tests/integration/services/query_service/test_integration_router_dependency.py",
    "tests/integration/services/query_service/test_main_app.py",
    "tests/integration/services/query_service/test_performance_router.py",
    "tests/integration/services/query_service/test_portfolios_router_dependency.py",
    "tests/integration/services/query_service/test_position_analytics_router.py",
    "tests/integration/services/query_service/test_positions_router_dependency.py",
    "tests/integration/services/query_service/test_operations_router_dependency.py",
    "tests/integration/services/query_service/test_reference_data_routers.py",
    "tests/integration/services/query_service/test_review_router.py",
    "tests/integration/services/query_service/test_risk_router_dependency.py",
    "tests/integration/services/query_service/test_simulation_router_dependency.py",
    "tests/integration/services/query_service/test_summary_router.py",
    "tests/integration/services/query_service/test_transactions_router.py",
]

SOURCE = "src/services/query_service/app"
FAIL_UNDER = "95"


def run_pytest(args: list[str], coverage_file: str) -> None:
    env = os.environ.copy()
    env["COVERAGE_FILE"] = coverage_file
    cmd = [sys.executable, "-m", "pytest", *args, f"--cov={SOURCE}", "--cov-report="]
    subprocess.run(cmd, check=True, env=env)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> int:
    run_pytest(UNIT_ARGS, ".coverage.unit")
    run_pytest(INTEGRATION_LITE_ARGS, ".coverage.integration_lite")
    run([sys.executable, "-m", "coverage", "combine", ".coverage.unit", ".coverage.integration_lite"])
    run([sys.executable, "-m", "coverage", "report", f"--fail-under={FAIL_UNDER}"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
