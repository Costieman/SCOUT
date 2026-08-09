"""Collect bounded live historical-OHLCV evidence from Alpha Vantage."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trade_scout.data.historical_evidence import (
    HistoricalEvidenceCase,
    HistoricalEvidenceReport,
    evaluate_historical_ohlcv,
)
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("dates must use YYYY-MM-DD") from exc


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect repeatable historical raw-OHLCV evidence through the Alpha Vantage adapter. "
            "This is an evidence run, not automatic provider acceptance."
        )
    )
    parser.add_argument("--symbol", action="append", required=True, dest="symbols")
    parser.add_argument("--start", type=_date, required=True)
    parser.add_argument("--end", type=_date, required=True)
    parser.add_argument("--minimum-observations", type=int, required=True)
    parser.add_argument("--max-start-lag-days", type=int, default=10)
    parser.add_argument("--max-end-lag-days", type=int, default=10)
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

    if args.end < args.start:
        raise SystemExit("--end must be on or after --start")
    if args.minimum_observations < 1:
        raise SystemExit("--minimum-observations must be positive")

    output_root: Path = args.output_root
    raw_root = output_root / "raw"
    report_root = output_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)

    symbols = tuple(dict.fromkeys(symbol.strip() for symbol in args.symbols if symbol.strip()))
    if not symbols:
        raise SystemExit("at least one non-empty --symbol is required")

    cases = tuple(
        HistoricalEvidenceCase(
            case_id=f"{symbol}-{args.start.isoformat()}-{args.end.isoformat()}",
            provider_symbol=symbol,
            start=args.start,
            end=args.end,
            minimum_observations=args.minimum_observations,
            max_start_lag_days=args.max_start_lag_days,
            max_end_lag_days=args.max_end_lag_days,
        )
        for symbol in symbols
    )
    adapter = AlphaVantageAdapter.from_api_key(
        api_key,
        raw_root=raw_root,
        allow_full_history=True,
    )
    report = evaluate_historical_ohlcv(adapter, cases)
    payload = _payload(report)

    json_path = report_root / "historical-ohlcv-evidence.json"
    markdown_path = report_root / "historical-ohlcv-evidence.md"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0 if report.passed else 2


def _payload(report: HistoricalEvidenceReport) -> dict[str, object]:
    payload = asdict(report)
    payload["passed"] = report.passed
    payload["provider_accepted"] = False
    payload["acceptance_note"] = (
        "A passing run demonstrates the configured historical retrieval sample only. Provider "
        "acceptance still requires licensing/storage review, identity evidence, delisting and "
        "corporate-action characterization, cross-provider validation, and the complete Phase 1 gate."
    )
    return payload


def _markdown(payload: dict[str, object]) -> str:
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list | tuple):
        raise TypeError("historical evidence payload cases must be a sequence")

    lines = [
        "# Historical OHLCV evidence",
        "",
        f"Provider: `{payload['provider_id']}`",
        f"Configured evidence checks passed: **{payload['passed']}**",
        "",
        "| case | symbol | rows | first | last | passed |",
        "|---|---|---:|---|---|---|",
    ]
    for case in raw_cases:
        if not isinstance(case, dict):
            raise TypeError("historical evidence case payload must be an object")
        checks = case["checks"]
        if not isinstance(checks, list | tuple):
            raise TypeError("historical evidence checks must be a sequence")
        passed = all(str(check["state"]) == "PASS" for check in checks if isinstance(check, dict))
        lines.append(
            f"| {case['case_id']} | {case['provider_symbol']} | {case['observation_count']} | "
            f"{case['first_trade_date']} | {case['last_trade_date']} | {passed} |"
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
