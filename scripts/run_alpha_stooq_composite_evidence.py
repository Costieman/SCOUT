"""Run bounded Alpha Vantage + Stooq composite coverage evidence."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trade_scout.data.composite_evidence import build_composite_evidence
from trade_scout.data.contracts import InstrumentId, PriceRepresentation
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter
from trade_scout.data.providers.stooq import StooqAdapter, StooqInstrumentLink
from trade_scout.data.reconciliation import ReconciliationTolerance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure A+B agreement, disagreement, and one-sided session coverage."
    )
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help="ALPHA_SYMBOL,STOOQ_SYMBOL,CANONICAL_ID,STOOQ_LINK_ID,START,END",
    )
    parser.add_argument("--price-relative-tolerance", type=float, default=0.0)
    parser.add_argument("--volume-relative-tolerance", type=float, default=0.0)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/alpha-stooq-composite-evidence"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not configured")
    cases = tuple(_parse_case(value) for value in args.case)
    links = tuple(
        StooqInstrumentLink(query_symbol=item[1], provider_instrument_id=item[3]) for item in cases
    )
    alpha = AlphaVantageAdapter.from_api_key(
        api_key,
        raw_root=args.output_root / "raw" / "alpha_vantage",
        allow_full_history=False,
    )
    stooq = StooqAdapter.from_http(
        instrument_links=links,
        raw_root=args.output_root / "raw" / "stooq",
    )
    tolerance = ReconciliationTolerance(
        price_relative=args.price_relative_tolerance,
        volume_relative=args.volume_relative_tolerance,
    )
    reports: list[dict[str, object]] = []
    for alpha_symbol, stooq_symbol, canonical_id, stooq_id, start, end in cases:
        alpha_bars = tuple(
            alpha.get_daily_bars(
                DailyBarRequest(
                    start=start,
                    end=end,
                    provider_symbols=(alpha_symbol,),
                    adjustment=PriceRepresentation.RAW,
                    run_id=f"ab-composite:{canonical_id}:alpha",
                )
            )
        )
        stooq_bars = tuple(
            stooq.get_daily_bars(
                DailyBarRequest(
                    start=start,
                    end=end,
                    provider_symbols=(stooq_symbol,),
                    adjustment=PriceRepresentation.RAW,
                    run_id=f"ab-composite:{canonical_id}:stooq",
                )
            )
        )
        report = build_composite_evidence(
            instrument_id=InstrumentId(canonical_id),
            provider_a_id="alpha_vantage",
            provider_a_instrument_id=f"alpha_vantage:symbol:{alpha_symbol}",
            provider_a_bars=alpha_bars,
            provider_b_id="stooq",
            provider_b_instrument_id=stooq_id,
            provider_b_bars=stooq_bars,
            tolerance=tolerance,
        )
        reports.append(
            {
                "alpha_symbol": alpha_symbol,
                "stooq_symbol": stooq_symbol,
                "instrument_id": canonical_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "summary": asdict(report.summary),
                "rows": [
                    {
                        "trade_date": row.trade_date.isoformat(),
                        "state": row.state.value,
                        "differing_fields": list(row.differing_fields),
                        "canonicalizable_without_review": row.canonicalizable_without_review,
                    }
                    for row in report.rows
                ],
            }
        )
    payload = {
        "evaluation_id": "alpha-stooq-composite-evidence-v0.1",
        "canonical_dataset_written": False,
        "cases": reports,
    }
    report_root = args.output_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    path = report_root / "composite-evidence.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(path)
    return 0


def _parse_case(value: str) -> tuple[str, str, str, str, date, date]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 6:
        raise SystemExit("--case requires six comma-separated fields")
    alpha_symbol, stooq_symbol, canonical_id, stooq_id, start_raw, end_raw = parts
    start = date.fromisoformat(start_raw)
    end = date.fromisoformat(end_raw)
    if end < start:
        raise SystemExit("case END must be on or after START")
    if (end - start).days > 180:
        raise SystemExit("bounded A+B cases are limited to 180 calendar days")
    return alpha_symbol.upper(), stooq_symbol.upper(), canonical_id, stooq_id, start, end


if __name__ == "__main__":
    raise SystemExit(main())
