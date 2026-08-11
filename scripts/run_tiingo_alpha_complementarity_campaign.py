"""Measure Tiingo + Alpha Vantage coverage complementarity in bounded GitHub-safe batches.

The campaign retrieves raw observations in-memory, compares expected session coverage and OHLCV
agreement, and persists derived metadata only. It never promotes bars, fills gaps, averages provider
values, or changes provider acceptance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from trade_scout.data.composite_evidence import (
    CompositeCoverageState,
    build_composite_evidence,
)
from trade_scout.data.contracts import InstrumentId, PriceRepresentation
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.provider_complementarity import summarize_provider_complementarity
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter, AlphaVantageApiError
from trade_scout.data.providers.tiingo import (
    TiingoAdapter,
    TiingoApiError,
    TiingoInstrumentLink,
)
from trade_scout.data.reconciliation import ReconciliationTolerance
from trade_scout.data.session_completeness import expected_exchange_sessions

_DEFAULT_CONFIG = Path("configs/tiingo_alpha_complementarity_cases_v0.1.json")
_OUTPUT = Path("runtime/tiingo-alpha-complementarity/report.json")
_SCHEMA_VERSION = "tiingo-alpha-complementarity-cases-v0.1"
_TOLERANCE = ReconciliationTolerance(
    price_relative=1e-6,
    volume_relative=1e-6,
)


@dataclass(frozen=True, slots=True)
class CampaignCase:
    case_id: str
    symbol: str
    exchange: str
    tiingo_provider_instrument_id: str


@dataclass(frozen=True, slots=True)
class CampaignConfig:
    start_date: date
    end_date: date
    cases: tuple[CampaignCase, ...]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded Tiingo + Alpha Vantage complementarity campaign."
    )
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--max-cases", type=int, default=3)
    args = parser.parse_args()

    if args.offset < 0:
        raise SystemExit("--offset must be non-negative")
    if args.max_cases <= 0:
        raise SystemExit("--max-cases must be positive")

    tiingo_token = os.environ.get("TIINGO_API_TOKEN", "").strip()
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not tiingo_token or not alpha_key:
        raise SystemExit("TIINGO_API_TOKEN and ALPHA_VANTAGE_API_KEY are required")

    try:
        config = _load_config(args.config)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"complementarity config error: {exc}", file=sys.stderr)
        return 2

    selected = config.cases[args.offset : args.offset + args.max_cases]
    if not selected:
        print("no campaign cases selected", file=sys.stderr)
        return 2

    alpha = AlphaVantageAdapter.from_api_key(alpha_key)
    case_reports: list[dict[str, object]] = []
    stopped_on_provider_failure = False

    for case in selected:
        tiingo = TiingoAdapter.from_api_token(
            tiingo_token,
            instrument_links=(
                TiingoInstrumentLink(
                    query_symbol=case.symbol,
                    provider_instrument_id=case.tiingo_provider_instrument_id,
                ),
            ),
        )
        request = DailyBarRequest(
            start=config.start_date,
            end=config.end_date,
            provider_symbols=(case.symbol,),
            adjustment=PriceRepresentation.RAW,
            run_id=f"tiingo-alpha-complementarity:{case.case_id}",
        )

        try:
            tiingo_bars = tuple(tiingo.get_daily_bars(request))
        except TiingoApiError as exc:
            case_reports.append(_provider_failure(case, "tiingo", exc))
            stopped_on_provider_failure = True
            break

        try:
            alpha_bars = tuple(alpha.get_daily_bars(request))
        except AlphaVantageApiError as exc:
            case_reports.append(_provider_failure(case, "alpha_vantage", exc))
            stopped_on_provider_failure = True
            break

        evidence = build_composite_evidence(
            instrument_id=InstrumentId(f"provider-complementarity:{case.case_id}"),
            provider_a_id="tiingo",
            provider_a_instrument_id=case.tiingo_provider_instrument_id,
            provider_a_bars=tiingo_bars,
            provider_b_id="alpha_vantage",
            provider_b_instrument_id=f"alpha_vantage:symbol:{case.symbol}",
            provider_b_bars=alpha_bars,
            tolerance=_TOLERANCE,
        )
        expected = expected_exchange_sessions(
            exchange=case.exchange,
            start=config.start_date,
            end=config.end_date,
        )
        complementarity = summarize_provider_complementarity(
            evidence,
            expected_sessions=expected,
        )
        evidence_dates = {row.trade_date for row in evidence.rows}
        expected_dates = set(expected)
        case_reports.append(
            {
                "case_id": case.case_id,
                "symbol": case.symbol,
                "exchange": case.exchange,
                "status": "COMPARED",
                "summary": asdict(complementarity),
                "fractions": {
                    "tiingo_coverage": complementarity.provider_a_coverage_fraction,
                    "alpha_vantage_coverage": complementarity.provider_b_coverage_fraction,
                    "union_coverage": complementarity.union_coverage_fraction,
                    "union_gain_over_tiingo": complementarity.union_gain_over_a_fraction,
                    "union_gain_over_alpha_vantage": complementarity.union_gain_over_b_fraction,
                },
                "tiingo_only_sessions": [
                    row.trade_date.isoformat()
                    for row in evidence.rows
                    if row.state is CompositeCoverageState.A_ONLY
                ],
                "alpha_vantage_only_sessions": [
                    row.trade_date.isoformat()
                    for row in evidence.rows
                    if row.state is CompositeCoverageState.B_ONLY
                ],
                "both_missing_sessions": [
                    day.isoformat() for day in sorted(expected_dates - evidence_dates)
                ],
                "disagreement_sessions": [
                    {
                        "trade_date": row.trade_date.isoformat(),
                        "fields": list(row.differing_fields),
                    }
                    for row in evidence.rows
                    if row.state is CompositeCoverageState.BOTH_DISAGREE
                ],
            }
        )

    aggregate = _aggregate(case_reports)
    payload = {
        "schema_version": "tiingo-alpha-complementarity-report-v0.1",
        "evaluation_id": "tiingo-alpha-complementarity-campaign-v0.1",
        "start_date": config.start_date.isoformat(),
        "end_date": config.end_date.isoformat(),
        "requested_case_offset": args.offset,
        "requested_max_cases": args.max_cases,
        "selected_case_count": len(selected),
        "completed_case_count": sum(
            report.get("status") == "COMPARED" for report in case_reports
        ),
        "stopped_on_provider_failure": stopped_on_provider_failure,
        "aggregate": aggregate,
        "cases": case_reports,
        "canonical_fill_allowed": False,
        "canonical_dataset_written": False,
        "provider_acceptance_changed": False,
        "serving_selected": False,
        "raw_provider_payload_uploaded": False,
        "price_rows_promoted": 0,
        "bars_fabricated": 0,
    }
    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(_OUTPUT)
    return 1 if stopped_on_provider_failure else 0


def _load_config(path: Path) -> CampaignConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("campaign config must be an object")
    if set(payload) != {"schema_version", "start_date", "end_date", "cases"}:
        raise ValueError("campaign config has missing or unknown top-level fields")
    if payload["schema_version"] != _SCHEMA_VERSION:
        raise ValueError("unsupported campaign config schema")

    start = date.fromisoformat(_text(payload["start_date"], "start_date"))
    end = date.fromisoformat(_text(payload["end_date"], "end_date"))
    if end < start:
        raise ValueError("campaign end date must be on or after start date")
    if start < end.replace(year=end.year - 1):
        raise ValueError("campaign window is intentionally bounded to less than one year")

    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("campaign config requires at least one case")

    cases: list[CampaignCase] = []
    seen_ids: set[str] = set()
    seen_symbols: set[str] = set()
    expected_fields = {
        "case_id",
        "symbol",
        "exchange",
        "tiingo_provider_instrument_id",
    }
    for raw in raw_cases:
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise ValueError("campaign case has missing or unknown fields")
        case = CampaignCase(
            case_id=_text(raw["case_id"], "case_id"),
            symbol=_text(raw["symbol"], "symbol").upper(),
            exchange=_text(raw["exchange"], "exchange").upper(),
            tiingo_provider_instrument_id=_text(
                raw["tiingo_provider_instrument_id"],
                "tiingo_provider_instrument_id",
            ),
        )
        if case.case_id in seen_ids:
            raise ValueError(f"duplicate campaign case ID: {case.case_id}")
        if case.symbol in seen_symbols:
            raise ValueError(f"duplicate campaign symbol: {case.symbol}")
        expected_exchange_sessions(exchange=case.exchange, start=start, end=end)
        seen_ids.add(case.case_id)
        seen_symbols.add(case.symbol)
        cases.append(case)
    return CampaignConfig(start_date=start, end_date=end, cases=tuple(cases))


def _provider_failure(
    case: CampaignCase,
    provider_id: str,
    exc: BaseException,
) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "symbol": case.symbol,
        "exchange": case.exchange,
        "status": "PROVIDER_FAILURE",
        "provider_id": provider_id,
        "error_type": type(exc).__name__,
    }


def _aggregate(case_reports: list[dict[str, object]]) -> dict[str, object]:
    summaries = [
        report["summary"]
        for report in case_reports
        if report.get("status") == "COMPARED" and isinstance(report.get("summary"), dict)
    ]
    keys = (
        "expected_session_count",
        "provider_a_session_count",
        "provider_b_session_count",
        "union_session_count",
        "both_agree_count",
        "both_disagree_count",
        "provider_a_only_count",
        "provider_b_only_count",
        "both_missing_count",
    )
    totals = {
        key: sum(int(summary[key]) for summary in summaries if key in summary) for key in keys
    }
    expected = totals["expected_session_count"]
    totals["tiingo_coverage_fraction"] = _safe_fraction(
        totals["provider_a_session_count"], expected
    )
    totals["alpha_vantage_coverage_fraction"] = _safe_fraction(
        totals["provider_b_session_count"], expected
    )
    totals["union_coverage_fraction"] = _safe_fraction(totals["union_session_count"], expected)
    totals["union_gain_over_tiingo_fraction"] = _safe_fraction(
        totals["provider_b_only_count"], expected
    )
    totals["union_gain_over_alpha_vantage_fraction"] = _safe_fraction(
        totals["provider_a_only_count"], expected
    )
    return totals


def _safe_fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
