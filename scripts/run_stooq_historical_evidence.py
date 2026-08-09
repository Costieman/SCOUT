"""Collect bounded, resumable live historical-OHLCV evidence from Stooq."""

from __future__ import annotations

import argparse
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from trade_scout.data.historical_evidence import HistoricalEvidenceCase, evaluate_historical_ohlcv
from trade_scout.data.historical_runtime import (
    load_checkpoint,
    record_completed_case,
    record_failure,
    write_checkpoint,
)
from trade_scout.data.providers.stooq import (
    StooqAdapter,
    StooqApiError,
    StooqInstrumentLink,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect repeatable historical OHLCV evidence through the no-credential Stooq "
            "candidate adapter. Completed cases are checkpointed and exact source bytes are "
            "preserved under the runtime output root."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_specs",
        required=True,
        help=(
            "Repeatable case specification SYMBOL,LINK_ID,START,END,MINIMUM_OBSERVATIONS. "
            "LINK_ID must be an explicit evidence identity; ticker text is never promoted into "
            "canonical identity by this runner."
        ),
    )
    parser.add_argument("--max-start-lag-days", type=int, default=10)
    parser.add_argument("--max-end-lag-days", type=int, default=10)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay between repeated Stooq requests.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/stooq-historical-evidence"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    cases, links = _cases_and_links(args)
    if args.delay_seconds < 0:
        raise SystemExit("Stooq evidence delay must be non-negative")

    output_root: Path = args.output_root
    raw_root = output_root / "raw"
    report_root = output_root / "report"
    checkpoint_path = report_root / "historical-ohlcv-checkpoint.json"
    report_root.mkdir(parents=True, exist_ok=True)

    try:
        checkpoint = load_checkpoint(checkpoint_path, cases)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    adapter = StooqAdapter.from_http(instrument_links=links, raw_root=raw_root)
    completed = checkpoint.get("completed_cases")
    if not isinstance(completed, dict):
        raise SystemExit("historical evidence checkpoint completed_cases is invalid")

    failure: dict[str, str] | None = None
    for case in cases:
        if case.case_id in completed:
            continue
        try:
            report = evaluate_historical_ohlcv(
                adapter,
                (case,),
                pace=lambda: _pace(args.delay_seconds),
            )
        except StooqApiError as exc:
            record_failure(checkpoint, case_id=case.case_id, error=exc)
            write_checkpoint(checkpoint_path, checkpoint)
            failure = {
                "case_id": case.case_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            break
        record_completed_case(checkpoint, report.cases[0])
        write_checkpoint(checkpoint_path, checkpoint)
        _pace(args.delay_seconds)

    payload = _payload(cases, checkpoint)
    _write_reports(report_root, payload)

    if failure is not None:
        print("Stooq historical evidence paused after a provider failure.")
        print(f"Completed cases: {payload['completed_case_count']} / {payload['expected_case_count']}")
        print(f"Failed case: {failure['case_id']}")
        print(f"Provider error: {failure['error']}")
        print("Rerun the identical command to resume without repeating completed cases.")
        return 2

    markdown_path = report_root / "historical-ohlcv-evidence.md"
    print(markdown_path.read_text(encoding="utf-8"))
    return 0 if payload["passed"] is True else 2


def _cases_and_links(
    args: argparse.Namespace,
) -> tuple[tuple[HistoricalEvidenceCase, ...], tuple[StooqInstrumentLink, ...]]:
    if args.max_start_lag_days < 0 or args.max_end_lag_days < 0:
        raise SystemExit("coverage lag tolerances must be non-negative")

    parsed = tuple(_parse_case(spec, args) for spec in args.case_specs)
    cases = tuple(item[0] for item in parsed)
    links = tuple(item[1] for item in parsed)
    case_ids = [case.case_id for case in cases]
    symbols = [link.query_symbol.upper() for link in links]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit("Stooq evidence case specifications must be unique")
    if len(symbols) != len(set(symbols)):
        raise SystemExit("Stooq evidence currently requires one case per query symbol")
    return cases, links


def _parse_case(
    spec: str,
    args: argparse.Namespace,
) -> tuple[HistoricalEvidenceCase, StooqInstrumentLink]:
    parts = [item.strip() for item in spec.split(",")]
    if len(parts) != 5:
        raise SystemExit("--case must be SYMBOL,LINK_ID,START,END,MINIMUM_OBSERVATIONS")
    symbol, link_id, start_raw, end_raw, minimum_raw = parts
    if not symbol or not link_id:
        raise SystemExit("--case SYMBOL and LINK_ID must be non-empty")
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
        minimum = int(minimum_raw)
    except ValueError as exc:
        raise SystemExit("--case dates must be YYYY-MM-DD and minimum must be an integer") from exc

    normalized_symbol = symbol.upper()
    case_id = f"{normalized_symbol}:{link_id}:{start.isoformat()}:{end.isoformat()}"
    case = HistoricalEvidenceCase(
        case_id=case_id,
        provider_symbol=normalized_symbol,
        start=start,
        end=end,
        minimum_observations=minimum,
        max_start_lag_days=args.max_start_lag_days,
        max_end_lag_days=args.max_end_lag_days,
    )
    link = StooqInstrumentLink(
        query_symbol=normalized_symbol,
        provider_instrument_id=link_id,
    )
    return case, link


def _pace(delay_seconds: float) -> None:
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def _payload(
    cases: tuple[HistoricalEvidenceCase, ...],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    raw_completed = checkpoint.get("completed_cases")
    if not isinstance(raw_completed, dict):
        raise TypeError("historical evidence checkpoint completed_cases must be an object")
    ordered_results = [
        raw_completed[case.case_id] for case in cases if case.case_id in raw_completed
    ]
    complete = len(ordered_results) == len(cases)
    passed = complete and bool(ordered_results) and all(_case_passed(item) for item in ordered_results)
    return {
        "report_type": "stooq-historical-ohlcv-evidence-v0.1",
        "provider_id": "stooq",
        "passed": passed,
        "complete": complete,
        "expected_case_count": len(cases),
        "completed_case_count": len(ordered_results),
        "cases": ordered_results,
        "last_failure": checkpoint.get("last_failure"),
        "provider_accepted": False,
        "acceptance_note": (
            "A passing campaign demonstrates only the configured Stooq historical-retrieval "
            "sample and normalized repeatability. Adjustment semantics, inactive/delisted "
            "coverage, licensing/redistribution, cross-source identity reconciliation, and "
            "representative canonical storage remain separate acceptance gates."
        ),
    }


def _case_passed(case: object) -> bool:
    if not isinstance(case, dict):
        return False
    checks = case.get("checks")
    if not isinstance(checks, list):
        return False
    return bool(checks) and all(
        isinstance(check, dict) and str(check.get("state")) == "PASS" for check in checks
    )


def _write_reports(report_root: Path, payload: dict[str, Any]) -> None:
    json_path = report_root / "historical-ohlcv-evidence.json"
    markdown_path = report_root / "historical-ohlcv-evidence.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")


def _markdown(payload: dict[str, Any]) -> str:
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list):
        raise TypeError("historical evidence payload cases must be a list")

    lines = [
        "# Stooq historical OHLCV evidence",
        "",
        f"Completed cases: {payload['completed_case_count']} / {payload['expected_case_count']}",
        f"Configured evidence checks passed: **{payload['passed']}**",
        "",
        "| case | symbol | rows | first | last | passed |",
        "|---|---|---:|---|---|---|",
    ]
    for case in raw_cases:
        if not isinstance(case, dict):
            continue
        lines.append(
            f"| {case['case_id']} | {case['provider_symbol']} | {case['observation_count']} | "
            f"{case['first_trade_date']} | {case['last_trade_date']} | {_case_passed(case)} |"
        )

    failure = payload.get("last_failure")
    if isinstance(failure, dict):
        lines.extend(
            [
                "",
                f"Paused at: `{failure.get('case_id')}`",
                f"Provider error: `{failure.get('error')}`",
                "",
                "The checkpoint preserves completed cases for an identical rerun.",
            ]
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "**Stooq acceptance remains false.** " + str(payload["acceptance_note"]),
            "",
            "Exact Stooq responses are captured beneath the runtime output root and remain "
            "outside Git. No campaign result automatically mutates the acceptance ledger.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
