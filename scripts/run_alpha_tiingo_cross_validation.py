"""Run bounded raw-OHLCV validation between Alpha Vantage and Tiingo."""

from __future__ import annotations

import argparse
import hashlib
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
from trade_scout.data.providers.tiingo import (
    TiingoAdapter,
    TiingoApiError,
    TiingoInstrumentLink,
)
from trade_scout.data.reconciliation import ReconciliationTolerance


class CrossValidationConfigurationError(ValueError):
    """Raised when a saved checkpoint does not match the requested comparison cases."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare bounded Alpha Vantage and Tiingo raw daily OHLCV samples. "
            "Completed cases are checkpointed; no provider values are blended or repaired."
        )
    )
    parser.add_argument(
        "--case",
        action="append",
        required=True,
        help=(
            "SYMBOL,CANONICAL_INSTRUMENT_ID,TIINGO_PROVIDER_INSTRUMENT_ID,START,END. "
            "Dates use YYYY-MM-DD. Repeat for multiple cases."
        ),
    )
    parser.add_argument("--price-absolute-tolerance", type=float, default=0.0)
    parser.add_argument("--price-relative-tolerance", type=float, default=0.0)
    parser.add_argument("--volume-absolute-tolerance", type=float, default=0.0)
    parser.add_argument("--volume-relative-tolerance", type=float, default=0.0)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("runtime/alpha-tiingo-cross-validation"),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    tiingo_key = os.environ.get("TIINGO_API_KEY", "").strip()
    if not alpha_key:
        raise SystemExit("ALPHA_VANTAGE_API_KEY is not configured")
    if not tiingo_key:
        raise SystemExit("TIINGO_API_KEY is not configured")

    cases = tuple(_parse_case(spec) for spec in args.case)
    _ensure_unique_cases(cases)
    tolerance = ReconciliationTolerance(
        price_absolute=args.price_absolute_tolerance,
        price_relative=args.price_relative_tolerance,
        volume_absolute=args.volume_absolute_tolerance,
        volume_relative=args.volume_relative_tolerance,
    )
    output_root: Path = args.output_root
    report_root = output_root / "report"
    report_root.mkdir(parents=True, exist_ok=True)
    checkpoint_path = report_root / "checkpoint.json"
    checkpoint = _load_checkpoint(checkpoint_path, cases, tolerance)

    alpha = AlphaVantageAdapter.from_api_key(
        alpha_key,
        raw_root=output_root / "raw" / "alpha_vantage",
        allow_full_history=False,
    )
    tiingo = TiingoAdapter.from_api_token(
        tiingo_key,
        instrument_links=tuple(
            TiingoInstrumentLink(
                query_symbol=_symbol(case),
                provider_instrument_id=case.secondary_provider_instrument_id,
            )
            for case in cases
        ),
        raw_root=output_root / "raw" / "tiingo",
    )

    completed = checkpoint["completed_cases"]
    if not isinstance(completed, dict):
        raise SystemExit("cross-validation checkpoint completed_cases is invalid")
    failure: dict[str, str] | None = None

    for case in cases:
        if case.case_id in completed:
            continue
        symbol = _symbol(case)
        request = DailyBarRequest(
            start=case.start,
            end=case.end,
            provider_symbols=(symbol,),
            adjustment=PriceRepresentation.RAW,
            run_id=f"cross-provider-evidence:{case.case_id}",
        )
        try:
            primary = tuple(alpha.get_daily_bars(request))
            secondary = tuple(tiingo.get_daily_bars(request))
            report = evaluate_cross_provider_bars(
                case,
                primary_bars=primary,
                secondary_bars=secondary,
                tolerance=tolerance,
            )
        except (AlphaVantageApiError, TiingoApiError, ValueError) as exc:
            failure = {
                "case_id": case.case_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            checkpoint["last_failure"] = failure
            _write_checkpoint(checkpoint_path, checkpoint)
            break
        completed[case.case_id] = _report_payload(report)
        checkpoint["last_failure"] = None
        _write_checkpoint(checkpoint_path, checkpoint)

    payload = _combined_payload(cases, checkpoint)
    json_path = report_root / "cross-provider-evidence.json"
    markdown_path = report_root / "cross-provider-evidence.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")

    if failure is not None:
        print("Cross-provider evaluation paused after a provider/evidence failure.")
        print(f"Failed case: {failure['case_id']}")
        print(f"Error: {failure['error']}")
        print("Rerun the identical command later to resume completed cases.")
        return 2
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _parse_case(spec: str) -> CrossProviderEvidenceCase:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 5:
        raise SystemExit(
            "--case must be SYMBOL,CANONICAL_INSTRUMENT_ID,TIINGO_PROVIDER_INSTRUMENT_ID,START,END"
        )
    symbol, instrument_id, tiingo_id, start_raw, end_raw = parts
    if not symbol or not instrument_id or not tiingo_id:
        raise SystemExit("--case symbol and provider/canonical identities must be non-empty")
    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except ValueError as exc:
        raise SystemExit("--case dates must use YYYY-MM-DD") from exc
    return CrossProviderEvidenceCase(
        case_id=f"{symbol}-{start.isoformat()}-{end.isoformat()}",
        instrument_id=InstrumentId(instrument_id),
        primary_provider_id="alpha_vantage",
        primary_provider_instrument_id=f"alpha_vantage:symbol:{symbol}",
        secondary_provider_id="tiingo",
        secondary_provider_instrument_id=tiingo_id,
        start=start,
        end=end,
    )


def _symbol(case: CrossProviderEvidenceCase) -> str:
    prefix = "alpha_vantage:symbol:"
    if not case.primary_provider_instrument_id.startswith(prefix):
        raise CrossValidationConfigurationError("Alpha Vantage provider identity has invalid shape")
    return case.primary_provider_instrument_id.removeprefix(prefix)


def _ensure_unique_cases(cases: tuple[CrossProviderEvidenceCase, ...]) -> None:
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise SystemExit("cross-provider case IDs must be unique")
    symbols = [_symbol(case).upper() for case in cases]
    if len(symbols) != len(set(symbols)):
        raise SystemExit(
            "one case per symbol is supported per run; use a separate output root for another period"
        )


def _configuration_id(
    cases: tuple[CrossProviderEvidenceCase, ...],
    tolerance: ReconciliationTolerance,
) -> str:
    payload = {
        "cases": [
            {
                "case_id": case.case_id,
                "instrument_id": str(case.instrument_id),
                "primary_provider_instrument_id": case.primary_provider_instrument_id,
                "secondary_provider_instrument_id": case.secondary_provider_instrument_id,
                "start": case.start.isoformat(),
                "end": case.end.isoformat(),
            }
            for case in cases
        ],
        "tolerance": asdict(tolerance),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_checkpoint(
    path: Path,
    cases: tuple[CrossProviderEvidenceCase, ...],
    tolerance: ReconciliationTolerance,
) -> dict[str, object]:
    configuration_id = _configuration_id(cases, tolerance)
    if not path.exists():
        return {
            "runtime_id": "alpha-tiingo-cross-validation-v0.1",
            "configuration_id": configuration_id,
            "completed_cases": {},
            "last_failure": None,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CrossValidationConfigurationError("cross-validation checkpoint is unreadable") from exc
    if not isinstance(payload, dict):
        raise CrossValidationConfigurationError("cross-validation checkpoint root must be an object")
    if payload.get("runtime_id") != "alpha-tiingo-cross-validation-v0.1":
        raise CrossValidationConfigurationError("cross-validation checkpoint runtime is incompatible")
    if payload.get("configuration_id") != configuration_id:
        raise CrossValidationConfigurationError(
            "cross-validation checkpoint configuration does not match requested cases/tolerances"
        )
    if not isinstance(payload.get("completed_cases"), dict):
        raise CrossValidationConfigurationError("cross-validation completed_cases must be an object")
    return payload


def _write_checkpoint(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _report_payload(report: object) -> dict[str, object]:
    from trade_scout.data.cross_provider_evidence import CrossProviderEvidenceReport

    if not isinstance(report, CrossProviderEvidenceReport):
        raise TypeError("cross-provider report has unexpected type")
    return {
        "case_id": report.case.case_id,
        "instrument_id": str(report.case.instrument_id),
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
    cases: tuple[CrossProviderEvidenceCase, ...],
    checkpoint: dict[str, object],
) -> dict[str, object]:
    completed = checkpoint.get("completed_cases")
    if not isinstance(completed, dict):
        raise TypeError("cross-validation completed_cases must be an object")
    ordered = [completed[case.case_id] for case in cases if case.case_id in completed]
    unresolved = sum(
        int(item.get("unresolved_count", 0)) for item in ordered if isinstance(item, dict)
    )
    complete = len(ordered) == len(cases)
    return {
        "evaluation_id": "alpha-tiingo-cross-validation-v0.1",
        "primary_provider_id": "alpha_vantage",
        "secondary_provider_id": "tiingo",
        "expected_case_count": len(cases),
        "completed_case_count": len(ordered),
        "complete": complete,
        "unresolved_discrepancy_count": unresolved,
        "cases": ordered,
        "last_failure": checkpoint.get("last_failure"),
        "provider_accepted": False,
        "acceptance_note": (
            "This report is validation evidence only. Provider acceptance remains false until the "
            "full Phase 1 evidence gate is satisfied and unresolved discrepancies are reviewed."
        ),
    }


def _markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Alpha Vantage / Tiingo cross-provider evidence",
        "",
        f"Completed cases: {payload['completed_case_count']} / {payload['expected_case_count']}",
        f"Unresolved discrepancies: {payload['unresolved_discrepancy_count']}",
        "",
        "| case | comparisons | comparable | agreements | unresolved | not comparable |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    cases = payload.get("cases")
    if isinstance(cases, list):
        for case in cases:
            if isinstance(case, dict):
                lines.append(
                    f"| {case['case_id']} | {case['comparison_count']} | {case['comparable_count']} | "
                    f"{case['agreement_count']} | {case['unresolved_count']} | "
                    f"{case['not_comparable_count']} |"
                )
    lines.extend(
        [
            "",
            "**Provider acceptance remains false.** " + str(payload["acceptance_note"]),
            "",
            "Exact provider responses are preserved under the runtime raw roots and remain outside Git.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
