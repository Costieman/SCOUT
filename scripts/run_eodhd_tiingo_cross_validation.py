"""Run the checked-in bounded EODHD versus Tiingo raw-OHLCV validation campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.cross_provider_evidence import (
    CrossProviderEvidenceReport,
    evaluate_cross_provider_bars,
)
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.eodhd import (
    EodhdAdapter,
    EodhdApiError,
    EodhdHttpClient,
    EodhdInstrumentLink,
    EodhdRawStoreCapture,
)
from trade_scout.data.providers.eodhd_resilience import (
    EodhdClassifyingUrllibTransport,
    EodhdRetryingBytesTransport,
)
from trade_scout.data.providers.eodhd_secondary_validation import (
    EodhdSecondaryValidationCase,
    EodhdSecondaryValidationPlan,
    load_eodhd_secondary_validation_plan,
)
from trade_scout.data.providers.tiingo import TiingoAdapter, TiingoApiError, TiingoInstrumentLink
from trade_scout.data.raw_store import RawBatchStore
from trade_scout.data.reconciliation import ReconciliationTolerance

_DEFAULT_PLAN = Path("configs/eodhd_tiingo_secondary_validation_v0.1.json")
_DEFAULT_OUTPUT = Path("runtime/eodhd-tiingo-cross-validation")
_RUNTIME_ID = "eodhd-tiingo-cross-validation-v0.1"


class EodhdTiingoValidationError(ValueError):
    """Raised when checkpoint state is incompatible with the requested campaign."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare checked-in bounded EODHD and Tiingo raw daily OHLCV cases. "
            "Completed cases are checkpointed and provider values are never blended."
        )
    )
    parser.add_argument("--plan", type=Path, default=_DEFAULT_PLAN)
    parser.add_argument("--output-root", type=Path, default=_DEFAULT_OUTPUT)
    parser.add_argument("--price-absolute-tolerance", type=float, default=0.0)
    parser.add_argument("--price-relative-tolerance", type=float, default=0.0)
    parser.add_argument("--volume-absolute-tolerance", type=float, default=0.0)
    parser.add_argument("--volume-relative-tolerance", type=float, default=0.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    eodhd_key = os.environ.get("EODHD_API_TOKEN", "").strip()
    tiingo_key = os.environ.get("TIINGO_API_KEY", "").strip()
    if not eodhd_key:
        raise SystemExit("EODHD_API_TOKEN is not configured")
    if not tiingo_key:
        raise SystemExit("TIINGO_API_KEY is not configured")

    plan = load_eodhd_secondary_validation_plan(args.plan)
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
    checkpoint = _load_checkpoint(checkpoint_path, plan, tolerance)

    retry_transport = EodhdRetryingBytesTransport(EodhdClassifyingUrllibTransport())
    eodhd_client = EodhdHttpClient(
        eodhd_key,
        transport=retry_transport,
        raw_capture=EodhdRawStoreCapture(RawBatchStore(output_root / "raw" / "eodhd")),
    )
    eodhd = EodhdAdapter(
        eodhd_client,
        instrument_links=tuple(
            EodhdInstrumentLink(
                query_symbol=case.eodhd_symbol,
                provider_instrument_id=case.eodhd_provider_instrument_id,
            )
            for case in plan.cases
        ),
    )
    tiingo = TiingoAdapter.from_api_token(
        tiingo_key,
        instrument_links=tuple(
            TiingoInstrumentLink(
                query_symbol=case.tiingo_symbol,
                provider_instrument_id=case.tiingo_provider_instrument_id,
            )
            for case in plan.cases
        ),
        raw_root=output_root / "raw" / "tiingo",
    )

    completed = checkpoint.get("completed_cases")
    if not isinstance(completed, dict):
        raise EodhdTiingoValidationError("checkpoint completed_cases must be an object")
    failure: dict[str, str] | None = None
    for case in plan.cases:
        if case.case_id in completed:
            continue
        try:
            completed[case.case_id] = _run_case(
                case, eodhd=eodhd, tiingo=tiingo, tolerance=tolerance
            )
            checkpoint["last_failure"] = None
            _write_checkpoint(checkpoint_path, checkpoint)
        except (EodhdApiError, TiingoApiError, ValueError) as exc:
            failure = {
                "case_id": case.case_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            checkpoint["last_failure"] = failure
            _write_checkpoint(checkpoint_path, checkpoint)
            break

    payload = _combined_payload(plan, checkpoint)
    json_path = report_root / "cross-provider-evidence.json"
    markdown_path = report_root / "cross-provider-evidence.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    if failure is not None:
        print("EODHD/Tiingo validation paused after a provider or evidence failure.")
        print(f"Failed case: {failure['case_id']}")
        print(f"Error: {failure['error']}")
        print("Rerun the identical command later to resume without repeating completed cases.")
        return 2
    print(markdown_path.read_text(encoding="utf-8"))
    return 0


def _run_case(
    case: EodhdSecondaryValidationCase,
    *,
    eodhd: EodhdAdapter,
    tiingo: TiingoAdapter,
    tolerance: ReconciliationTolerance,
) -> dict[str, object]:
    primary = tuple(
        eodhd.get_daily_bars(
            DailyBarRequest(
                start=case.start,
                end=case.end,
                provider_symbols=(case.eodhd_symbol,),
                adjustment=PriceRepresentation.RAW,
                run_id=f"eodhd-tiingo:{case.case_id}:eodhd",
            )
        )
    )
    secondary = tuple(
        tiingo.get_daily_bars(
            DailyBarRequest(
                start=case.start,
                end=case.end,
                provider_symbols=(case.tiingo_symbol,),
                adjustment=PriceRepresentation.RAW,
                run_id=f"eodhd-tiingo:{case.case_id}:tiingo",
            )
        )
    )
    report = evaluate_cross_provider_bars(
        case.evidence_case(),
        primary_bars=primary,
        secondary_bars=secondary,
        tolerance=tolerance,
    )
    return _report_payload(report)


def _configuration_id(
    plan: EodhdSecondaryValidationPlan,
    tolerance: ReconciliationTolerance,
) -> str:
    payload = {
        "version": plan.version,
        "cases": [
            {
                "case_id": case.case_id,
                "eodhd_symbol": case.eodhd_symbol,
                "tiingo_symbol": case.tiingo_symbol,
                "instrument_id": str(case.instrument_id),
                "eodhd_provider_instrument_id": case.eodhd_provider_instrument_id,
                "tiingo_provider_instrument_id": case.tiingo_provider_instrument_id,
                "start": case.start.isoformat(),
                "end": case.end.isoformat(),
            }
            for case in plan.cases
        ],
        "tolerance": asdict(tolerance),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_checkpoint(
    path: Path,
    plan: EodhdSecondaryValidationPlan,
    tolerance: ReconciliationTolerance,
) -> dict[str, object]:
    configuration_id = _configuration_id(plan, tolerance)
    if not path.exists():
        return {
            "runtime_id": _RUNTIME_ID,
            "configuration_id": configuration_id,
            "completed_cases": {},
            "last_failure": None,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EodhdTiingoValidationError("cross-validation checkpoint is unreadable") from exc
    if not isinstance(payload, dict):
        raise EodhdTiingoValidationError("cross-validation checkpoint root must be an object")
    if payload.get("runtime_id") != _RUNTIME_ID:
        raise EodhdTiingoValidationError("cross-validation checkpoint runtime is incompatible")
    if payload.get("configuration_id") != configuration_id:
        raise EodhdTiingoValidationError(
            "cross-validation checkpoint does not match the current plan/tolerances"
        )
    if not isinstance(payload.get("completed_cases"), dict):
        raise EodhdTiingoValidationError("checkpoint completed_cases must be an object")
    return payload


def _write_checkpoint(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _report_payload(report: CrossProviderEvidenceReport) -> dict[str, object]:
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
    plan: EodhdSecondaryValidationPlan,
    checkpoint: dict[str, object],
) -> dict[str, object]:
    completed = checkpoint.get("completed_cases")
    if not isinstance(completed, dict):
        raise EodhdTiingoValidationError("checkpoint completed_cases must be an object")
    ordered = [completed[case.case_id] for case in plan.cases if case.case_id in completed]
    unresolved = sum(
        int(item.get("unresolved_count", 0)) for item in ordered if isinstance(item, dict)
    )
    return {
        "evaluation_id": _RUNTIME_ID,
        "plan_version": plan.version,
        "primary_provider_id": "eodhd",
        "secondary_provider_id": "tiingo",
        "expected_case_count": len(plan.cases),
        "completed_case_count": len(ordered),
        "complete": len(ordered) == len(plan.cases),
        "unresolved_discrepancy_count": unresolved,
        "cases": ordered,
        "last_failure": checkpoint.get("last_failure"),
        "representative_sample_accepted": False,
        "provider_accepted": False,
        "acceptance_note": (
            "This bounded campaign is secondary-validation evidence only. It cannot accept EODHD, "
            "cannot establish representative-scale coverage, and cannot resolve disagreements "
            "without explicit review."
        ),
    }


def _markdown(payload: dict[str, object]) -> str:
    lines = [
        "# EODHD / Tiingo cross-provider evidence",
        "",
        f"Plan: `{payload['plan_version']}`",
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
                    f"| {case['case_id']} | {case['comparison_count']} | "
                    f"{case['comparable_count']} | {case['agreement_count']} | "
                    f"{case['unresolved_count']} | {case['not_comparable_count']} |"
                )
    lines.extend(
        ["", "**Provider acceptance remains false.** " + str(payload["acceptance_note"]), ""]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
