"""Run bounded raw-OHLCV validation between Alpha Vantage and Stooq."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

from trade_scout.data.contracts import InstrumentId, PriceRepresentation
from trade_scout.data.cross_provider_evidence import (
    CrossProviderEvidenceCase,
    evaluate_cross_provider_bars,
)
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter, AlphaVantageApiError
from trade_scout.data.providers.stooq import (
    StooqAdapter,
    StooqApiError,
    StooqInstrumentLink,
)
from trade_scout.data.reconciliation import ReconciliationTolerance


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare bounded Alpha Vantage and Stooq daily OHLCV samples. "
            "The comparison is evidence-only: provider values are never averaged, "
            "filled, or promoted automatically."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help=(
            "ALPHA_SYMBOL,STOOQ_SYMBOL,CANONICAL_INSTRUMENT_ID,STOOQ_LINK_ID,START,END. "
            "Repeat for multiple explicitly reviewed identity links."
        ),
    )
    parser.add_argument("--price-absolute-tolerance", type=float, default=0.0)
    parser.add_argument("--price-relative-tolerance", type=float, default=0.0)
    parser.add_argument("--volume-absolute-tolerance", type=float, default=0.0)
    parser.add_argument("--volume-relative-tolerance", type=float, default=0.0)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/alpha-stooq-cross-validation"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if not alpha_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not configured")

    parsed = tuple(_parse_case(spec) for spec in args.case)
    _ensure_unique_cases(parsed)
    tolerance = ReconciliationTolerance(
        price_absolute=args.price_absolute_tolerance,
        price_relative=args.price_relative_tolerance,
        volume_absolute=args.volume_absolute_tolerance,
        volume_relative=args.volume_relative_tolerance,
    )

    output_root: Path = args.output_root
    report_root = output_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)

    alpha = AlphaVantageAdapter.from_api_key(
        alpha_key,
        raw_root=output_root / "raw" / "alpha_vantage",
        allow_full_history=False,
    )
    stooq = StooqAdapter.from_http(
        instrument_links=tuple(
            StooqInstrumentLink(
                query_symbol=item.stooq_symbol,
                provider_instrument_id=item.case.secondary_provider_instrument_id,
            )
            for item in parsed
        ),
        raw_root=output_root / "raw" / "stooq",
    )

    reports = []
    failure: dict[str, str] | None = None
    for item in parsed:
        request_alpha = DailyBarRequest(
            start=item.case.start,
            end=item.case.end,
            provider_symbols=(item.alpha_symbol,),
            adjustment=PriceRepresentation.RAW,
            run_id=f"alpha-stooq:{item.case.case_id}:alpha",
        )
        request_stooq = DailyBarRequest(
            start=item.case.start,
            end=item.case.end,
            provider_symbols=(item.stooq_symbol,),
            adjustment=PriceRepresentation.RAW,
            run_id=f"alpha-stooq:{item.case.case_id}:stooq",
        )
        try:
            alpha_bars = tuple(alpha.get_daily_bars(request_alpha))
            stooq_bars = tuple(stooq.get_daily_bars(request_stooq))
            report = evaluate_cross_provider_bars(
                item.case,
                primary_bars=alpha_bars,
                secondary_bars=stooq_bars,
                tolerance=tolerance,
            )
        except (AlphaVantageApiError, StooqApiError, ValueError) as exc:
            failure = {
                "case_id": item.case.case_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            break
        reports.append(_report_payload(report, item.alpha_symbol, item.stooq_symbol))

    payload = _combined_payload(parsed, reports, failure, tolerance)
    json_path = report_root / "alpha-stooq-cross-provider-evidence.json"
    markdown_path = report_root / "alpha-stooq-cross-provider-evidence.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")

    if failure is not None:
        print(markdown_path.read_text(encoding="utf-8"))
        return 2
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


class _ParsedCase:
    def __init__(
        self,
        *,
        case: CrossProviderEvidenceCase,
        alpha_symbol: str,
        stooq_symbol: str,
    ) -> None:
        self.case = case
        self.alpha_symbol = alpha_symbol
        self.stooq_symbol = stooq_symbol


def _parse_case(spec: str) -> _ParsedCase:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 6:
        raise SystemExit(
            "--case must be ALPHA_SYMBOL,STOOQ_SYMBOL,CANONICAL_INSTRUMENT_ID,"
            "STOOQ_LINK_ID,START,END"
        )
    alpha_symbol, stooq_symbol, instrument_id, stooq_id, start_raw, end_raw = parts
    if not all((alpha_symbol, stooq_symbol, instrument_id, stooq_id)):
        raise SystemExit("--case symbols and identity fields must be non-empty")
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except ValueError as exc:
        raise SystemExit("--case dates must use YYYY-MM-DD") from exc
    if end < start:
        raise SystemExit("--case END must be on or after START")
    if (end - start).days > 180:
        raise SystemExit(
            "Alpha Vantage free/compact evaluation cases are limited to at most 180 calendar days"
        )
    alpha_symbol = alpha_symbol.upper()
    stooq_symbol = stooq_symbol.upper()
    case = CrossProviderEvidenceCase(
        case_id=f"{alpha_symbol}-{start.isoformat()}-{end.isoformat()}",
        instrument_id=InstrumentId(instrument_id),
        primary_provider_id="alpha_vantage",
        primary_provider_instrument_id=f"alpha_vantage:symbol:{alpha_symbol}",
        secondary_provider_id="stooq",
        secondary_provider_instrument_id=stooq_id,
        start=start,
        end=end,
    )
    return _ParsedCase(case=case, alpha_symbol=alpha_symbol, stooq_symbol=stooq_symbol)


def _ensure_unique_cases(cases: tuple[_ParsedCase, ...]) -> None:
    case_ids = [item.case.case_id for item in cases]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit("cross-provider case IDs must be unique")
    stooq_symbols = [item.stooq_symbol for item in cases]
    if len(stooq_symbols) != len(set(stooq_symbols)):
        raise SystemExit("one Stooq symbol per comparison run is supported")


def _report_payload(report: object, alpha_symbol: str, stooq_symbol: str) -> dict[str, object]:
    from trade_scout.data.cross_provider_evidence import CrossProviderEvidenceReport

    if not isinstance(report, CrossProviderEvidenceReport):
        raise TypeError("cross-provider report has unexpected type")
    return {
        "case_id": report.case.case_id,
        "instrument_id": str(report.case.instrument_id),
        "alpha_symbol": alpha_symbol,
        "stooq_symbol": stooq_symbol,
        "start": report.case.start.isoformat(),
        "end": report.case.end.isoformat(),
        "comparison_count": report.summary.comparison_count,
        "comparable_count": report.summary.comparable_count,
        "agreement_count": report.summary.agreement_count,
        "unresolved_count": report.summary.unresolved_count,
        "not_comparable_count": report.summary.not_comparable_count,
        "comparable_fraction": report.summary.comparable_fraction,
        "agreement_fraction_of_comparable": report.summary.agreement_fraction_of_comparable,
        "results": [asdict(result) for result in report.results],
    }


def _combined_payload(
    cases: tuple[_ParsedCase, ...],
    reports: list[dict[str, object]],
    failure: dict[str, str] | None,
    tolerance: ReconciliationTolerance,
) -> dict[str, object]:
    unresolved = sum(int(item["unresolved_count"]) for item in reports)
    not_comparable = sum(int(item["not_comparable_count"]) for item in reports)
    return {
        "evaluation_id": "alpha-stooq-cross-validation-v0.1",
        "primary_provider_id": "alpha_vantage",
        "secondary_provider_id": "stooq",
        "expected_case_count": len(cases),
        "completed_case_count": len(reports),
        "complete": failure is None and len(reports) == len(cases),
        "tolerance": asdict(tolerance),
        "unresolved_discrepancy_count": unresolved,
        "not_comparable_count": not_comparable,
        "cases": reports,
        "last_failure": failure,
        "provider_accepted": False,
        "canonical_fill_allowed": False,
        "interpretation": (
            "This run identifies agreement, disagreement, and one-sided session coverage between "
            "Alpha Vantage and Stooq. It does not average feeds, synthesize missing bars, or decide "
            "that either provider is canonical. Stooq adjustment semantics and identity links remain "
            "separate acceptance gates."
        ),
    }


def _markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Alpha Vantage / Stooq cross-provider evidence",
        "",
        f"Completed cases: {payload['completed_case_count']} / {payload['expected_case_count']}",
        f"Unresolved discrepancies: {payload['unresolved_discrepancy_count']}",
        f"Not-comparable sessions: {payload['not_comparable_count']}",
        "",
        "| case | comparisons | comparable | agreements | unresolved | not comparable |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    cases = payload.get("cases")
    if isinstance(cases, list):
        for case in cases:
            if isinstance(case, dict):
                lines.append(
                    f"| {case['case_id']} | {case['comparison_count']} | "
                    f"{case['comparable_count']} | {case['agreement_count']} | "
                    f"{case['unresolved_count']} | {case['not_comparable_count']} |"
                )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            str(payload["interpretation"]),
            "",
            "**Canonical fill remains disabled. Provider acceptance remains false.**",
            "",
        ]
    )
    if payload.get("last_failure") is not None:
        lines.extend(["## Failure", "", f"`{payload['last_failure']}`", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
