"""Single source of truth for CI/local test suite composition."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SUITES: dict[str, list[str]] = {
    "unit": ["tests/unit/services/query_service"],
    "integration-lite": [
        "tests/integration/services/query_service/test_capabilities_router_dependency.py",
        "tests/integration/services/query_service/test_concentration_router.py",
        "tests/integration/services/query_service/test_integration_router_dependency.py",
        "tests/integration/services/query_service/test_main_app.py",
        "tests/integration/services/query_service/test_performance_router.py",
        "tests/integration/services/query_service/test_portfolios_router_dependency.py",
        "tests/integration/services/query_service/test_position_analytics_router.py",
        "tests/integration/services/query_service/test_positions_router_dependency.py",
        "tests/integration/services/query_service/test_operations_router_dependency.py",
        "tests/integration/services/query_service/test_reference_data_routers.py",
        "tests/integration/services/query_service/test_lookup_contract_router.py",
        "tests/integration/services/query_service/test_review_router.py",
        "tests/integration/services/query_service/test_risk_router_dependency.py",
        "tests/integration/services/query_service/test_simulation_router_dependency.py",
        "tests/integration/services/query_service/test_summary_router.py",
        "tests/integration/services/query_service/test_transactions_router.py",
    ],
    "e2e-smoke": [
        "tests/e2e/test_query_service_observability.py",
        "tests/e2e/test_complex_portfolio_lifecycle.py",
    ],
}

SOURCE = "src/services/query_service/app"


def get_suite(name: str) -> list[str]:
    try:
        return SUITES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown suite: {name}") from exc


def validate_suite_paths(name: str) -> None:
    missing = [path for path in get_suite(name) if not Path(path).exists()]
    if missing:
        raise FileNotFoundError(
            f"Suite '{name}' has missing test paths:\n"
            + "\n".join(f" - {path}" for path in missing)
        )


def run_suite(
    name: str,
    *,
    quiet: bool = False,
    with_coverage: bool = False,
    coverage_file: str | None = None,
) -> int:
    validate_suite_paths(name)

    cmd = [sys.executable, "-m", "pytest", *get_suite(name)]
    if quiet:
        cmd.append("-q")
    if with_coverage:
        cmd.extend([f"--cov={SOURCE}", "--cov-report="])

    env = os.environ.copy()
    if coverage_file:
        env["COVERAGE_FILE"] = coverage_file

    return subprocess.run(cmd, check=False, env=env).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or inspect CI test suite definitions.")
    parser.add_argument(
        "--suite",
        choices=sorted(SUITES.keys()),
        required=True,
        help="Suite name to run or inspect.",
    )
    parser.add_argument(
        "--print-args",
        action="store_true",
        help="Print pytest args for the suite and exit.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Run pytest with -q.",
    )
    parser.add_argument(
        "--with-coverage",
        action="store_true",
        help="Add --cov and --cov-report= to pytest invocation.",
    )
    parser.add_argument(
        "--coverage-file",
        default=None,
        help="Set COVERAGE_FILE while running the suite.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate suite paths and exit.",
    )
    args = parser.parse_args()

    validate_suite_paths(args.suite)

    if args.print_args:
        print(" ".join(get_suite(args.suite)))
        return 0

    if args.validate_only:
        print(f"Suite '{args.suite}' is valid ({len(get_suite(args.suite))} entries).")
        return 0

    return run_suite(
        args.suite,
        quiet=args.quiet,
        with_coverage=args.with_coverage,
        coverage_file=args.coverage_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
