"""Collect bounded, resumable live historical-OHLCV evidence from Alpha Vantage."""

from __future__ import annotations

import argparse
import json
import os
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
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter, AlphaVantageApiError


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect repeatable historical raw-OHLCV evidence through the Alpha Vantage adapter. "
            "Completed cases are checkpointed and provider failures can be resumed later."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_specs",
        help=(
            "Repeatable case specification SYMBOL,START,END,MINIMUM_OBSERVATIONS. "
            "Use this form to evaluate multiple symbols and date periods in one run."
        ),
    )
    parser.add_argument("--symbol", action="append", dest="symbols")
    parser.add_argument("--start", type=_date)
    parser.add_argument("--end", type=_date)
    parser.add_argument("--minimum-observations", type=int)
    parser.add_argument("--max-start-lag-days", type=int, default=10)
    parser.add_argument("--max-end-lag-days", type=int, default=10)
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=None,
        help="Delay between provider requests; defaults to ALPHA_VANTAGE_EVIDENCE_DELAY_SECONDS or 0.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/alpha-vantage-historical-evidence"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not configured")

    cases = _cases(args)
    delay_seconds = _delay_seconds(args.delay_seconds)
    output_root: Path = args.output_root
    raw_root = output_root / "raw"
    report_root = output_root / "report"
    checkpoint_path = report_root / "historical-ohlcv-checkpoint.json"
    report_root.mkdir(parents=True, exist_ok=True)

    try:
        checkpoint = load_checkpoint(checkpoint_path, cases)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    adapter = AlphaVantageAdapter.from_api_key(
        api_key,
        raw_root=raw_root,
        allow_full_history=True,
    )
    failure: dict[str, str] | None = None
    completed = checkpoint["completed_cases"]
    if not isinstance(completed, dict):
        raise SystemExit("historical evidence checkpoint completed_cases is invalid")

    for case in cases:
        if case.case_id in completed:
            continue
        try:
            report = evaluate_historical_ohlcv(
                adapter,
                (case,),
                pace=lambda: _pace(delay_seconds),
            )
        except AlphaVantageApiError as exc:
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
        _pace(delay_seconds)

    payload = _payload(adapter.provider_id, cases, checkpoint)
    _write_reports(report_root, payload)

    if failure is not None:
        print("Historical OHLCV evaluation paused after a provider failure.")
        print(
            f"Completed cases: {payload['completed_case_count']} / {payload['expected_case_count']}"
        )
        print(f"Failed case: {failure['case_id']}")
        print(f"Provider error: {failure['error']}")
        print("Rerun the identical command later to resume without repeating completed cases.")
        return 2

    markdown_path = report_root / "historical-ohlcv-evidence.md"
    print(markdown_path.read_text(encoding="utf-8"))
    return 0 if payload["passed"] is True else 2


def _cases(args: argparse.Namespace) -> tuple[HistoricalEvidenceCase, ...]:
    if args.case_specs:
        if any(
            value is not None
            for value in (args.symbols, args.start, args.end, args.minimum_observations)
        ):
            raise SystemExit("use either --case or the legacy --symbol/--start/--end options")
        cases = tuple(_parse_case_spec(spec, args) for spec in args.case_specs)
    else:
        if not args.symbols or args.start is None or args.end is None:
            raise SystemExit("provide at least one --case or --symbol with --start and --end")
        if args.minimum_observations is None:
            raise SystemExit("--minimum-observations is required with legacy --symbol mode")
        symbols = tuple(dict.fromkeys(symbol.strip() for symbol in args.symbols if symbol.strip()))
        cases = tuple(
            _make_case(
                symbol=symbol,
                start=args.start,
                end=args.end,
                minimum=args.minimum_observations,
                args=args,
            )
            for symbol in symbols
        )
    if not cases:
        raise SystemExit("historical evidence requires at least one case")
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit("historical evidence case specifications must be unique")
    return cases


def _parse_case_spec(spec: str, args: argparse.Namespace) -> HistoricalEvidenceCase:
    parts = [item.strip() for item in spec.split(",")]
    if len(parts) != 4:
        raise SystemExit("--case must be SYMBOL,START,END,MINIMUM_OBSERVATIONS")
    symbol, start_raw, end_raw, minimum_raw = parts
    if not symbol:
        raise SystemExit("--case symbol must be non-empty")
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
        minimum = int(minimum_raw)
    except ValueError as exc:
        raise SystemExit("--case dates must be YYYY-MM-DD and minimum must be an integer") from exc
    return _make_case(symbol=symbol, start=start, end=end, minimum=minimum, args=args)


def _make_case(
    *,
    symbol: str,
    start: date,
    end: date,
    minimum: int,
    args: argparse.Namespace,
) -> HistoricalEvidenceCase:
    return HistoricalEvidenceCase(
        case_id=f"{symbol}-{start.isoformat()}-{end.isoformat()}",
        provider_symbol=symbol,
        start=start,
        end=end,
        minimum_observations=minimum,
        max_start_lag_days=args.max_start_lag_days,
        max_end_lag_days=args.max_end_lag_days,
    )


def _delay_seconds(argument: float | None) -> float:
    if argument is None:
        raw = os.environ.get("ALPHA_VANTAGE_EVIDENCE_DELAY_SECONDS", "0").strip()
        try:
            delay = float(raw)
        except ValueError as exc:
            raise SystemExit("ALPHA_VANTAGE_EVIDENCE_DELAY_SECONDS must be numeric") from exc
    else:
        delay = argument
    if delay < 0:
        raise SystemExit("historical evidence delay must be non-negative")
    return delay


def _pace(delay_seconds: float) -> None:
    if delay_seconds > 0:
        time.sleep(delay_seconds)


def _payload(
    provider_id: str,
    cases: tuple[HistoricalEvidenceCase, ...],
    checkpoint: dict[str, Any],
) -> dict[str, Any]:
    raw_completed = checkpoint.get("completed_cases")
    if not isinstance(raw_completed, dict):
        raise TypeError("historical evidence checkpoint completed_cases must be an object")
    ordered_results = [
        raw_completed[case.case_id] for case in cases if case.case_id in raw_completed
    ]
    case_passes = [_case_passed(result) for result in ordered_results]
    complete = len(ordered_results) == len(cases)
    passed = complete and bool(ordered_results) and all(case_passes)
    return {
        "provider_id": provider_id,
        "passed": passed,
        "complete": complete,
        "expected_case_count": len(cases),
        "completed_case_count": len(ordered_results),
        "cases": ordered_results,
        "last_failure": checkpoint.get("last_failure"),
        "provider_accepted": False,
        "acceptance_note": (
            "A passing run demonstrates the configured historical retrieval sample only. Provider "
            "acceptance still requires licensing/storage review, identity evidence, delisting and "
            "corporate-action characterization, cross-provider validation, and the complete Phase "
            "1 gate."
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
        "# Historical OHLCV evidence",
        "",
        f"Provider: `{payload['provider_id']}`",
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
            "**Provider acceptance remains false.** " + str(payload["acceptance_note"]),
            "",
            "Exact raw provider responses are captured under the configured runtime output root. "
            "They remain outside Git and are not promoted automatically.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
