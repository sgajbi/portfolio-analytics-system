"""Install editable packages and dev tooling for local/CI quality gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def discover_editable_projects() -> list[Path]:
    pyprojects = sorted(ROOT.glob("src/**/pyproject.toml"))
    return [path.parent for path in pyprojects]


def main() -> int:
    projects = discover_editable_projects()
    for project_dir in projects:
        run([sys.executable, "-m", "pip", "install", "-e", str(project_dir)])

    run([sys.executable, "-m", "pip", "install", "-r", "tests/requirements.txt"])
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "ruff",
            "mypy",
            "types-python-dateutil",
        ]
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
