"""Collect bounded live evidence about Stooq split-adjustment behavior."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.stooq import StooqAdapter, StooqInstrumentLink
from trade_scout.data.providers.stooq_adjustment_evidence import (
    StooqAdjustmentEvidenceState,
    characterize_stooq_split_semantics,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Retrieve bounded Stooq windows around externally verified split events and compare "
            "the observed close discontinuity with raw-like and split-adjusted-like hypotheses."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="case_specs",
        required=True,
        help=(
            "Repeatable SYMBOL,LINK_ID,SPLIT_DATE,SPLIT_RATIO,START,END specification. "
            "Split facts must come from an independently reviewed source."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/stooq-split-semantics-evidence"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    cases = tuple(_parse_case(item) for item in args.case_specs)
    symbols = [case[0] for case in cases]
    if len(symbols) != len(set(symbols)):
        raise SystemExit("split semantics evidence currently requires one case per Stooq symbol")

    output_root: Path = args.output_root
    raw_root = output_root / "raw"
    report_root = output_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)

    links = tuple(
        StooqInstrumentLink(query_symbol=case[0], provider_instrument_id=case[1]) for case in cases
    )
    adapter = StooqAdapter.from_http(instrument_links=links, raw_root=raw_root)

    evidence = []
    for symbol, _link_id, split_date, split_ratio, start, end in cases:
        bars = adapter.get_daily_bars(
            DailyBarRequest(start=start, end=end, provider_symbols=(symbol,))
        )
        evidence.append(
            characterize_stooq_split_semantics(
                bars,
                symbol=symbol,
                split_date=split_date,
                split_ratio=split_ratio,
            )
        )

    states = [item.state for item in evidence]
    consistent = (
        bool(states)
        and len(set(states)) == 1
        and states[0] is not StooqAdjustmentEvidenceState.INCONCLUSIVE
    )
    payload: dict[str, Any] = {
        "report_type": "stooq-split-semantics-evidence-v0.1",
        "provider_id": "stooq",
        "consistent_non_inconclusive_behavior": consistent,
        "candidate_behavior": states[0] if consistent else None,
        "cases": [asdict(item) for item in evidence],
        "provider_accepted": False,
        "interpretation": (
            "This report characterizes behavior around caller-supplied split events only. "
            "Even consistent evidence does not establish all Stooq adjustment or corporate-action "
            "semantics and does not change canonical acceptance automatically."
        ),
    }
    json_path = report_root / "stooq-split-semantics-evidence.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    markdown_path = report_root / "stooq-split-semantics-evidence.md"
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(markdown_path.read_text(encoding="utf-8"))
    return 0 if consistent else 2


def _parse_case(spec: str) -> tuple[str, str, date, float, date, date]:
    parts = [item.strip() for item in spec.split(",")]
    if len(parts) != 6:
        raise SystemExit("--case must be SYMBOL,LINK_ID,SPLIT_DATE,SPLIT_RATIO,START,END")
    symbol, link_id, split_raw, ratio_raw, start_raw, end_raw = parts
    if not symbol or not link_id:
        raise SystemExit("split semantics SYMBOL and LINK_ID must be non-empty")
    try:
        split_date = date.fromisoformat(split_raw)
        split_ratio = float(ratio_raw)
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except ValueError as exc:
        raise SystemExit("split semantics dates/ratio are invalid") from exc
    if not start < split_date <= end:
        raise SystemExit("split semantics window must span the supplied split date")
    return symbol.upper(), link_id, split_date, split_ratio, start, end


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Stooq split-semantics evidence",
        "",
        f"Consistent non-inconclusive behavior: **{payload['consistent_non_inconclusive_behavior']}**",
        f"Candidate behavior: `{payload['candidate_behavior']}`",
        "",
        "| symbol | split date | ratio | pre close | post close | state |",
        "|---|---|---:|---:|---:|---|",
    ]
    raw_cases = payload.get("cases")
    if isinstance(raw_cases, list):
        for case in raw_cases:
            if isinstance(case, dict):
                lines.append(
                    f"| {case['symbol']} | {case['split_date']} | {case['split_ratio']} | "
                    f"{case['pre_close']} | {case['post_close']} | {case['state']} |"
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
