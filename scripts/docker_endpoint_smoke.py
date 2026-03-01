"""Deterministic docker endpoint smoke runner for lotus-core.

This script boots (or reuses) the local docker stack, executes a deterministic
ingest->query flow with unique identifiers, and validates a fixed endpoint
status matrix for ingestion and query services.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


@dataclass(slots=True)
class CheckResult:
    name: str
    method: str
    url: str
    status: int
    ok: bool
    note: str
    response: Any


def _run(cmd: list[str], cwd: Path) -> None:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        print(f"Command failed ({completed.returncode}): {' '.join(cmd)}", file=sys.stderr)
        if completed.stdout:
            print(completed.stdout, file=sys.stderr)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        raise RuntimeError("command failed")


def _compose_up_with_retry(*, compose_file: str, repo_root: Path, build: bool) -> None:
    up_cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
    if build:
        up_cmd.append("--build")

    attempts = 2
    for attempt in range(1, attempts + 1):
        try:
            _run(up_cmd, cwd=repo_root)
            return
        except RuntimeError:
            if attempt == attempts:
                raise
            # Handle transient Kafka/ZK startup races by recycling containers once.
            _run(["docker", "compose", "-f", compose_file, "down"], cwd=repo_root)
            time.sleep(5)


def _call(
    results: list[CheckResult],
    *,
    name: str,
    method: str,
    url: str,
    expected: set[int],
    **kwargs: Any,
) -> requests.Response | None:
    try:
        response = requests.request(method=method, url=url, timeout=40, **kwargs)
        content_type = response.headers.get("content-type", "")
        body: Any
        if "application/json" in content_type:
            try:
                body = response.json()
            except ValueError:
                body = response.text[:1000]
        else:
            body = response.text[:1000] if response.text else None
        ok = response.status_code in expected
        results.append(
            CheckResult(
                name=name,
                method=method,
                url=url,
                status=response.status_code,
                ok=ok,
                note="",
                response=body,
            )
        )
        return response
    except Exception as exc:  # pragma: no cover - defensive runtime capture
        results.append(
            CheckResult(
                name=name,
                method=method,
                url=url,
                status=0,
                ok=False,
                note=str(exc),
                response=None,
            )
        )
        return None


def _wait_ready(base_url: str, timeout_seconds: int) -> None:
    ready_url = f"{base_url}/health/ready"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(ready_url, timeout=5)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for ready endpoint: {ready_url}")


def _wait_portfolio_visible(query_base_url: str, portfolio_id: str, timeout_seconds: int) -> None:
    url = f"{query_base_url}/portfolios/{portfolio_id}"
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=8)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(
        f"Timed out waiting for portfolio to appear in query service: {portfolio_id}"
    )


def _write_report(
    *,
    output_dir: Path,
    run_id: str,
    summary: dict[str, Any],
    results: list[CheckResult],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        **summary,
        "results": [asdict(item) for item in results],
    }
    json_path = output_dir / f"{run_id}-docker-endpoint-smoke.json"
    md_path = output_dir / f"{run_id}-docker-endpoint-smoke.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    failures = [item for item in results if not item.ok]
    lines = [
        f"# Docker Endpoint Smoke {run_id}",
        "",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Portfolio: {summary['portfolio_id']}",
        f"- Security: {summary['security_id']}",
        f"- ISIN: {summary['isin']}",
        "",
    ]
    if failures:
        lines.append("## Failures")
        for failure in failures:
            lines.append(
                f"- {failure.name} `{failure.method} {failure.url}` -> {failure.status} ({failure.note})"
            )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run deterministic lotus-core docker endpoint smoke."
    )
    parser.add_argument("--repo-root", default=".", help="Path to lotus-core repository root.")
    parser.add_argument(
        "--compose-file", default="docker-compose.yml", help="Docker compose file path."
    )
    parser.add_argument("--ingestion-base-url", default="http://localhost:8200")
    parser.add_argument("--query-base-url", default="http://localhost:8201")
    parser.add_argument("--output-dir", default="output/task-runs")
    parser.add_argument(
        "--reset-volumes", action="store_true", help="Run docker compose down -v first."
    )
    parser.add_argument("--build", action="store_true", help="Run compose up with --build.")
    parser.add_argument(
        "--skip-compose", action="store_true", help="Do not run docker compose commands."
    )
    parser.add_argument("--ready-timeout-seconds", type=int, default=180)
    parser.add_argument("--query-visible-timeout-seconds", type=int, default=120)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    compose_file = str((repo_root / args.compose_file).resolve())

    if not args.skip_compose:
        if args.reset_volumes:
            _run(["docker", "compose", "-f", compose_file, "down", "-v"], cwd=repo_root)
        _compose_up_with_retry(compose_file=compose_file, repo_root=repo_root, build=args.build)

    _wait_ready(args.ingestion_base_url, args.ready_timeout_seconds)
    _wait_ready(args.query_base_url, args.ready_timeout_seconds)

    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    portfolio_id = f"PORT_SMOKE_{run_id}"
    security_id = f"SEC_SMOKE_{run_id}"
    instrument_id = f"INST_SMOKE_{run_id}"
    transaction_id = f"TX_SMOKE_{run_id}"
    transaction_id_2 = f"TX2_SMOKE_{run_id}"
    csv_transaction_id = f"TXUP_SMOKE_{run_id}"
    isin = f"US{run_id.replace('-', '')[-10:]}"
    now_utc = datetime.now(UTC).replace(microsecond=0)
    trade_timestamp = now_utc.isoformat().replace("+00:00", "Z")
    trade_date = trade_timestamp[:10]

    tmp_csv = repo_root / ".tmp_upload_tx.csv"
    with tmp_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "transaction_id",
                "portfolio_id",
                "instrument_id",
                "security_id",
                "transaction_date",
                "transaction_type",
                "quantity",
                "price",
                "gross_transaction_amount",
                "trade_currency",
                "currency",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "transaction_id": csv_transaction_id,
                "portfolio_id": portfolio_id,
                "instrument_id": instrument_id,
                "security_id": security_id,
                "transaction_date": trade_timestamp,
                "transaction_type": "BUY",
                "quantity": "1",
                "price": "10",
                "gross_transaction_amount": "10",
                "trade_currency": "USD",
                "currency": "USD",
            }
        )

    results: list[CheckResult] = []
    ingest = args.ingestion_base_url
    query = args.query_base_url

    _call(results, name="ing live", method="GET", url=f"{ingest}/health/live", expected={200})
    _call(results, name="ing ready", method="GET", url=f"{ingest}/health/ready", expected={200})
    _call(results, name="ing metrics", method="GET", url=f"{ingest}/metrics", expected={200})
    _call(
        results,
        name="ops set normal",
        method="PUT",
        url=f"{ingest}/ingestion/ops/control",
        expected={200},
        json={"mode": "normal", "updated_by": "deterministic_smoke"},
    )

    _call(
        results,
        name="ingest business dates",
        method="POST",
        url=f"{ingest}/ingest/business-dates",
        expected={202},
        json={"business_dates": [{"business_date": trade_date}]},
    )
    _call(
        results,
        name="ingest fx rates",
        method="POST",
        url=f"{ingest}/ingest/fx-rates",
        expected={202},
        json={
            "fx_rates": [
                {
                    "from_currency": "USD",
                    "to_currency": "CHF",
                    "rate": 0.9,
                    "rate_date": trade_date,
                }
            ]
        },
    )
    _call(
        results,
        name="ingest instruments",
        method="POST",
        url=f"{ingest}/ingest/instruments",
        expected={202},
        json={
            "instruments": [
                {
                    "security_id": security_id,
                    "isin": isin,
                    "name": "Smoke Asset",
                    "currency": "USD",
                    "product_type": "Equity",
                    "asset_class": "Equity",
                }
            ]
        },
    )
    _call(
        results,
        name="ingest portfolios",
        method="POST",
        url=f"{ingest}/ingest/portfolios",
        expected={202},
        json={
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2024-01-01",
                    "risk_exposure": "Medium",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Discretionary",
                    "booking_center_code": "SGP",
                    "client_id": "CLIENT_SMOKE_001",
                    "status": "Active",
                }
            ]
        },
    )
    _call(
        results,
        name="ingest market prices",
        method="POST",
        url=f"{ingest}/ingest/market-prices",
        expected={202},
        json={
            "market_prices": [
                {
                    "security_id": security_id,
                    "price": 180.25,
                    "currency": "USD",
                    "price_date": trade_date,
                }
            ]
        },
    )
    _call(
        results,
        name="ingest transaction",
        method="POST",
        url=f"{ingest}/ingest/transaction",
        expected={202},
        json={
            "transaction_id": transaction_id,
            "portfolio_id": portfolio_id,
            "instrument_id": instrument_id,
            "security_id": security_id,
            "transaction_date": trade_timestamp,
            "transaction_type": "BUY",
            "quantity": 10,
            "price": 180.25,
            "gross_transaction_amount": 1802.5,
            "trade_currency": "USD",
            "currency": "USD",
        },
    )
    _call(
        results,
        name="ingest transactions",
        method="POST",
        url=f"{ingest}/ingest/transactions",
        expected={202},
        json={
            "transactions": [
                {
                    "transaction_id": transaction_id_2,
                    "portfolio_id": portfolio_id,
                    "instrument_id": instrument_id,
                    "security_id": security_id,
                    "transaction_date": trade_timestamp,
                    "transaction_type": "BUY",
                    "quantity": 2,
                    "price": 181.0,
                    "gross_transaction_amount": 362.0,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ]
        },
    )
    _call(
        results,
        name="ingest portfolio bundle",
        method="POST",
        url=f"{ingest}/ingest/portfolio-bundle",
        expected={202},
        json={
            "source_system": "SMOKE",
            "mode": "UPSERT",
            "business_dates": [{"business_date": trade_date}],
            "portfolios": [
                {
                    "portfolio_id": portfolio_id,
                    "base_currency": "USD",
                    "open_date": "2024-01-01",
                    "risk_exposure": "Medium",
                    "investment_time_horizon": "Long",
                    "portfolio_type": "Discretionary",
                    "booking_center_code": "SGP",
                    "client_id": "CLIENT_SMOKE_001",
                    "status": "Active",
                }
            ],
            "instruments": [
                {
                    "security_id": security_id,
                    "isin": isin,
                    "name": "Smoke Asset",
                    "currency": "USD",
                    "product_type": "Equity",
                }
            ],
            "market_prices": [
                {
                    "security_id": security_id,
                    "price": 180.25,
                    "currency": "USD",
                    "price_date": trade_date,
                }
            ],
            "fx_rates": [
                {
                    "from_currency": "USD",
                    "to_currency": "CHF",
                    "rate": 0.9,
                    "rate_date": trade_date,
                }
            ],
            "transactions": [
                {
                    "transaction_id": f"TXB_SMOKE_{run_id}",
                    "portfolio_id": portfolio_id,
                    "instrument_id": instrument_id,
                    "security_id": security_id,
                    "transaction_date": trade_timestamp,
                    "transaction_type": "BUY",
                    "quantity": 1,
                    "price": 180.25,
                    "gross_transaction_amount": 180.25,
                    "trade_currency": "USD",
                    "currency": "USD",
                }
            ],
        },
    )

    with tmp_csv.open("rb") as handle:
        _call(
            results,
            name="upload preview",
            method="POST",
            url=f"{ingest}/ingest/uploads/preview",
            expected={200},
            files={"file": ("smoke.csv", handle, "text/csv")},
            data={"entity_type": "transactions", "sample_size": "5"},
        )

    with tmp_csv.open("rb") as handle:
        _call(
            results,
            name="upload commit",
            method="POST",
            url=f"{ingest}/ingest/uploads/commit",
            expected={202},
            files={"file": ("smoke.csv", handle, "text/csv")},
            data={"entity_type": "transactions", "allow_partial": "true"},
        )

    jobs_response = _call(
        results,
        name="jobs list",
        method="GET",
        url=f"{ingest}/ingestion/jobs?limit=10",
        expected={200},
    )
    job_id: str | None = None
    if jobs_response is not None and jobs_response.status_code == 200:
        payload = jobs_response.json()
        jobs = payload.get("jobs") or payload.get("data") or []
        if jobs:
            job_id = jobs[0].get("job_id")
    if job_id:
        _call(
            results,
            name="job get",
            method="GET",
            url=f"{ingest}/ingestion/jobs/{job_id}",
            expected={200},
        )
        _call(
            results,
            name="job failures",
            method="GET",
            url=f"{ingest}/ingestion/jobs/{job_id}/failures",
            expected={200},
        )
        _call(
            results,
            name="job retry dry run",
            method="POST",
            url=f"{ingest}/ingestion/jobs/{job_id}/retry",
            expected={200},
            json={"dry_run": True, "record_keys": []},
        )
    else:
        results.append(
            CheckResult(
                name="job get",
                method="GET",
                url=f"{ingest}/ingestion/jobs/{{job_id}}",
                status=0,
                ok=False,
                note="job_id not discovered from list response",
                response=None,
            )
        )

    _call(
        results,
        name="health summary",
        method="GET",
        url=f"{ingest}/ingestion/health/summary",
        expected={200},
    )
    _call(
        results,
        name="health lag",
        method="GET",
        url=f"{ingest}/ingestion/health/lag",
        expected={200},
    )
    _call(
        results,
        name="health slo",
        method="GET",
        url=f"{ingest}/ingestion/health/slo",
        expected={200},
    )
    _call(
        results,
        name="dlq list",
        method="GET",
        url=f"{ingest}/ingestion/dlq/consumer-events?limit=10",
        expected={200},
    )
    _call(
        results,
        name="reprocess tx",
        method="POST",
        url=f"{ingest}/reprocess/transactions",
        expected={202},
        json={"transaction_ids": [transaction_id]},
    )

    _wait_portfolio_visible(
        query_base_url=query,
        portfolio_id=portfolio_id,
        timeout_seconds=args.query_visible_timeout_seconds,
    )

    _call(results, name="query live", method="GET", url=f"{query}/health/live", expected={200})
    _call(results, name="query ready", method="GET", url=f"{query}/health/ready", expected={200})
    _call(results, name="query metrics", method="GET", url=f"{query}/metrics", expected={200})
    _call(
        results,
        name="portfolios list",
        method="GET",
        url=f"{query}/portfolios/?portfolio_id={portfolio_id}",
        expected={200},
    )
    _call(
        results,
        name="portfolio get",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}",
        expected={200},
    )
    _call(
        results,
        name="positions",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/positions",
        expected={200},
    )
    _call(
        results,
        name="position history",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/position-history?security_id={security_id}",
        expected={200},
    )
    _call(
        results,
        name="transactions",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/transactions",
        expected={200},
    )
    _call(
        results,
        name="cash linkage",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/transactions/{transaction_id}/cash-linkage",
        expected={200, 404},
    )
    _call(
        results,
        name="lots",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/positions/{security_id}/lots",
        expected={200},
    )
    _call(
        results,
        name="accrued offsets",
        method="GET",
        url=f"{query}/portfolios/{portfolio_id}/positions/{security_id}/accrued-offsets",
        expected={200},
    )
    _call(
        results,
        name="support overview",
        method="GET",
        url=f"{query}/support/portfolios/{portfolio_id}/overview",
        expected={200},
    )
    _call(
        results,
        name="support valuation jobs",
        method="GET",
        url=f"{query}/support/portfolios/{portfolio_id}/valuation-jobs",
        expected={200},
    )
    _call(
        results,
        name="support aggregation jobs",
        method="GET",
        url=f"{query}/support/portfolios/{portfolio_id}/aggregation-jobs",
        expected={200},
    )
    _call(
        results,
        name="lineage keys",
        method="GET",
        url=f"{query}/lineage/portfolios/{portfolio_id}/keys",
        expected={200},
    )
    _call(
        results,
        name="lineage security",
        method="GET",
        url=f"{query}/lineage/portfolios/{portfolio_id}/securities/{security_id}",
        expected={200, 404},
    )
    _call(
        results,
        name="prices",
        method="GET",
        url=f"{query}/prices/?security_id={security_id}",
        expected={200},
    )
    _call(
        results,
        name="fx rates",
        method="GET",
        url=f"{query}/fx-rates/?from_currency=USD&to_currency=CHF",
        expected={200},
    )
    _call(
        results,
        name="instruments",
        method="GET",
        url=f"{query}/instruments/?security_id={security_id}",
        expected={200},
    )
    _call(
        results,
        name="lookups portfolios",
        method="GET",
        url=f"{query}/lookups/portfolios?limit=50",
        expected={200},
    )
    _call(
        results,
        name="lookups instruments",
        method="GET",
        url=f"{query}/lookups/instruments?limit=50",
        expected={200},
    )
    _call(
        results,
        name="lookups currencies",
        method="GET",
        url=f"{query}/lookups/currencies?limit=50",
        expected={200},
    )
    _call(
        results,
        name="integration capabilities",
        method="GET",
        url=f"{query}/integration/capabilities",
        expected={200},
    )
    _call(
        results,
        name="integration policy",
        method="GET",
        url=f"{query}/integration/policy/effective",
        expected={200},
    )
    _call(
        results,
        name="enrichment bulk",
        method="POST",
        url=f"{query}/integration/instruments/enrichment-bulk",
        expected={200},
        json={"security_ids": [security_id]},
    )
    _call(
        results,
        name="core snapshot",
        method="POST",
        url=f"{query}/integration/portfolios/{portfolio_id}/core-snapshot",
        expected={200},
        json={
            "as_of_date": trade_date,
            "snapshot_mode": "BASELINE",
            "sections": ["positions_baseline", "portfolio_totals"],
        },
    )

    session_response = _call(
        results,
        name="simulation create",
        method="POST",
        url=f"{query}/simulation-sessions",
        expected={200, 201},
        json={"portfolio_id": portfolio_id, "created_by": "deterministic_smoke", "ttl_hours": 1},
    )
    session_id: str | None = None
    if session_response is not None and session_response.status_code in {200, 201}:
        body = session_response.json()
        session_id = body.get("session_id")
    if session_id:
        _call(
            results,
            name="simulation get",
            method="GET",
            url=f"{query}/simulation-sessions/{session_id}",
            expected={200},
        )
        _call(
            results,
            name="simulation changes upsert",
            method="POST",
            url=f"{query}/simulation-sessions/{session_id}/changes",
            expected={200, 201},
            json={
                "changes": [
                    {
                        "change_type": "TRANSACTION",
                        "transaction": {
                            "transaction_id": f"SIMTX_SMOKE_{run_id}",
                            "portfolio_id": portfolio_id,
                            "instrument_id": instrument_id,
                            "security_id": security_id,
                            "transaction_date": trade_timestamp,
                            "transaction_type": "BUY",
                            "quantity": 1,
                            "price": 180.25,
                            "gross_transaction_amount": 180.25,
                            "trade_currency": "USD",
                            "currency": "USD",
                        },
                    }
                ]
            },
        )
        _call(
            results,
            name="simulation projected positions",
            method="GET",
            url=f"{query}/simulation-sessions/{session_id}/projected-positions",
            expected={200},
        )
        _call(
            results,
            name="simulation projected summary",
            method="GET",
            url=f"{query}/simulation-sessions/{session_id}/projected-summary",
            expected={200},
        )
        _call(
            results,
            name="simulation delete",
            method="DELETE",
            url=f"{query}/simulation-sessions/{session_id}",
            expected={200, 204},
        )

    try:
        tmp_csv.unlink(missing_ok=True)
    except Exception:
        pass

    failures = [item for item in results if not item.ok]
    summary = {
        "run_id": run_id,
        "portfolio_id": portfolio_id,
        "security_id": security_id,
        "isin": isin,
        "passed": len(results) - len(failures),
        "failed": len(failures),
    }
    json_path, md_path = _write_report(
        output_dir=(repo_root / args.output_dir),
        run_id=run_id,
        summary=summary,
        results=results,
    )

    print(f"Wrote: {json_path}")
    print(f"Wrote: {md_path}")
    print(f"Passed: {summary['passed']} Failed: {summary['failed']}")
    if failures:
        print("Failed checks:")
        for item in failures:
            print(f"- {item.name}: status={item.status} note={item.note}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
