"""Collect bounded live evidence about Stooq inactive/delisted-history coverage."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.stooq import StooqAdapter, StooqInstrumentLink
from trade_scout.data.providers.stooq_inactive_evidence import (
    StooqInactiveEvidenceState,
    characterize_stooq_inactive_history,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve bounded Stooq histories for independently identified inactive securities and "
            "compare the observed final date with caller-supplied lifecycle evidence."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_specs",
        required=True,
        help=(
            "Repeatable SYMBOL,LINK_ID,START,END,EXPECTED_TERMINAL_DATE specification. "
            "Use NONE when the external source confirms inactivity but not a precise terminal date."
        ),
    )
    parser.add_argument("--terminal-tolerance-days", type=int, default=10)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/stooq-inactive-evidence"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.terminal_tolerance_days < 0:
        raise SystemExit("terminal tolerance must be non-negative")
    cases = tuple(_parse_case(spec) for spec in args.case_specs)
    symbols = [case[0] for case in cases]
    if len(symbols) != len(set(symbols)):
        raise SystemExit("inactive evidence currently requires one case per Stooq symbol")

    output_root: Path = args.output_root
    raw_root = output_root / "raw"
    report_root = output_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    links = tuple(
        StooqInstrumentLink(query_symbol=symbol, provider_instrument_id=link_id)
        for symbol, link_id, _start, _end, _terminal in cases
    )
    adapter = StooqAdapter.from_http(instrument_links=links, raw_root=raw_root)

    evidence = []
    for symbol, _link_id, start, end, terminal_date in cases:
        bars = adapter.get_daily_bars(
            DailyBarRequest(start=start, end=end, provider_symbols=(symbol,))
        )
        evidence.append(
            characterize_stooq_inactive_history(
                bars,
                symbol=symbol,
                expected_terminal_date=terminal_date,
                terminal_tolerance_days=args.terminal_tolerance_days,
            )
        )

    informative_states = {
        StooqInactiveEvidenceState.HISTORY_PRESENT_TERMINAL_ALIGNED,
        StooqInactiveEvidenceState.HISTORY_PRESENT_TERMINAL_MISMATCH,
        StooqInactiveEvidenceState.NO_HISTORY,
    }
    characterized = bool(evidence) and all(item.state in informative_states for item in evidence)
    payload: dict[str, Any] = {
        "report_type": "stooq-inactive-delisted-evidence-v0.1",
        "provider_id": "stooq",
        "characterized": characterized,
        "case_count": len(evidence),
        "history_present_count": sum(item.observation_count > 0 for item in evidence),
        "no_history_count": sum(
            item.state is StooqInactiveEvidenceState.NO_HISTORY for item in evidence
        ),
        "terminal_aligned_count": sum(
            item.state is StooqInactiveEvidenceState.HISTORY_PRESENT_TERMINAL_ALIGNED
            for item in evidence
        ),
        "cases": [asdict(item) for item in evidence],
        "provider_accepted": False,
        "interpretation": (
            "This evidence describes Stooq behavior only for independently identified inactive "
            "securities and supplied query symbols. It does not establish complete historical "
            "delisted-universe coverage, terminal returns, bankruptcy outcomes, symbol continuity, "
            "or canonical provider acceptance."
        ),
    }
    json_path = report_root / "stooq-inactive-evidence.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path = report_root / "stooq-inactive-evidence.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0 if characterized else 2


def _parse_case(spec: str) -> tuple[str, str, date, date, date | None]:
    parts = [item.strip() for item in spec.split(",")]
    if len(parts) != 5:
        raise SystemExit("--case must be SYMBOL,LINK_ID,START,END,EXPECTED_TERMINAL_DATE")
    symbol, link_id, start_raw, end_raw, terminal_raw = parts
    if not symbol or not link_id:
        raise SystemExit("inactive evidence SYMBOL and LINK_ID must be non-empty")
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
        terminal = None if terminal_raw.upper() == "NONE" else date.fromisoformat(terminal_raw)
    except ValueError as exc:
        raise SystemExit("inactive evidence dates must use YYYY-MM-DD or NONE") from exc
    if end < start:
        raise SystemExit("inactive evidence END must be on or after START")
    if terminal is not None and not start <= terminal <= end:
        raise SystemExit("expected terminal date must fall inside the requested evidence window")
    return symbol.upper(), link_id, start, end, terminal


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Stooq inactive/delisted coverage evidence",
        "",
        f"Cases: **{payload['case_count']}**",
        f"Characterized: **{payload['characterized']}**",
        f"Histories present: **{payload['history_present_count']}**",
        f"No-history cases: **{payload['no_history_count']}**",
        "",
        "| symbol | expected terminal | rows | first | last | terminal error | state |",
        "|---|---|---:|---|---|---:|---|",
    ]
    raw_cases = payload.get("cases")
    if isinstance(raw_cases, list):
        for case in raw_cases:
            if not isinstance(case, dict):
                continue
            lines.append(
                f"| {case['symbol']} | {case['expected_terminal_date']} | "
                f"{case['observation_count']} | {case['first_trade_date']} | "
                f"{case['last_trade_date']} | {case['terminal_date_error_days']} | "
                f"{case['state']} |"
            )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            str(payload["interpretation"]),
            "",
            "Exact Stooq responses remain under the ignored runtime output root.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
