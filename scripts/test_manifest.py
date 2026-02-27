"""Single source of truth for CI/local test suite composition."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _discover_integration_lite() -> list[str]:
    query_integration_root = Path("tests/integration/services/query_service")
    router_like = sorted(query_integration_root.glob("test_*router*.py"))
    explicit = [query_integration_root / "test_main_app.py"]
    combined = [*router_like, *explicit]
    return [str(path).replace("\\", "/") for path in sorted(set(combined))]


SUITES: dict[str, list[str]] = {
    "unit": ["tests/unit"],
    "unit-db": [
        "tests/unit/libs/portfolio-common/test_position_state_repository.py",
        "tests/unit/services/calculators/position_valuation_calculator/repositories/test_unit_valuation_repo.py",
    ],
    "integration-lite": _discover_integration_lite(),
    "e2e-smoke": [
        "tests/e2e/test_query_service_observability.py",
        "tests/e2e/test_complex_portfolio_lifecycle.py",
    ],
}

SOURCE = "src/services/query_service/app"
SUITE_PYTEST_ARGS: dict[str, list[str]] = {
    "unit": ["-m", "not integration_db"],
}


def get_suite(name: str) -> list[str]:
    try:
        return SUITES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown suite: {name}") from exc


def validate_suite_paths(name: str) -> None:
    missing = [
        path for path in get_suite(name) if not path.startswith("-") and not Path(path).exists()
    ]
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

    cmd = [sys.executable, "-m", "pytest", *get_suite(name), *SUITE_PYTEST_ARGS.get(name, [])]
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
