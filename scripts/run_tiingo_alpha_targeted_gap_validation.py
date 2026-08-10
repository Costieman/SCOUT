"""Validate known Tiingo coverage gaps with independent Alpha Vantage evidence.

The command is intentionally evidence-only. It verifies the private Tiingo durable profile, derives
expected sessions from the pinned exchange calendar, captures the exact Alpha Vantage response in
the private workspace, and emits metadata-only coverage evidence. It never fills or promotes bars.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.contracts import PriceRepresentation
from trade_scout.data.provider import DailyBarRequest
from trade_scout.data.providers.alpha_vantage import AlphaVantageAdapter, AlphaVantageApiError
from trade_scout.data.providers.tiingo_profile import TiingoProfileError, profile_durable_tiingo
from trade_scout.data.targeted_gap_validation import (
    TargetedGapCase,
    TargetedGapValidationError,
    evaluate_targeted_gap_validator,
    expected_target_gap_sessions,
)

_DEFAULT_CONFIG = Path("configs/tiingo_alpha_targeted_gap_cases_v0.1.json")
_SCHEMA_VERSION = "tiingo-alpha-targeted-gap-cases-v0.1"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect independent-provider evidence for reviewed Tiingo coverage gaps."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG)
    parser.add_argument("--case-id")
    parser.add_argument(
        "--request-alpha-full-history",
        action="store_true",
        help=(
            "Explicitly request Alpha Vantage outputsize=full. This does not assert or change "
            "account entitlement; provider rejection remains an inconclusive provider failure."
        ),
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable workspace evidence is inconsistent; targeted gap validation is blocked"
            )
        cases = _load_cases(repository_root / args.config)
        if args.case_id is not None:
            cases = tuple(case for case in cases if case.case_id == args.case_id)
            if not cases:
                raise TargetedGapValidationError(f"unknown targeted gap case: {args.case_id}")
        if not args.request_alpha_full_history:
            raise TargetedGapValidationError(
                "historical validator request is blocked until --request-alpha-full-history is "
                "explicitly supplied; the flag requests full output but does not assume entitlement"
            )

        api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
        if not api_key:
            raise TargetedGapValidationError("ALPHA_VANTAGE_API_KEY is not configured")

        tiingo_profile = profile_durable_tiingo(
            receipt_root=workspace.tiingo_receipts_root,
            raw_root=workspace.tiingo_raw_root,
            storage_namespace=workspace.manifest.storage_namespace,
        )
        profile_by_symbol = {item.source_symbol: item for item in tiingo_profile.symbols}

        reports: list[dict[str, object]] = []
        fail_closed = False
        for case in cases:
            symbol_profile = profile_by_symbol.get(case.symbol)
            if symbol_profile is None:
                raise TargetedGapValidationError(
                    f"durable Tiingo profile does not contain targeted symbol {case.symbol}"
                )
            if symbol_profile.first_date != case.observed_first_date.isoformat():
                raise TargetedGapValidationError(
                    f"durable Tiingo first date changed for {case.symbol}: "
                    f"{symbol_profile.first_date} != {case.observed_first_date.isoformat()}"
                )

            expected_sessions = expected_target_gap_sessions(case)
            raw_root = (
                workspace.root
                / "providers"
                / "alpha_vantage"
                / "targeted-gap-validation"
                / case.case_id
                / "raw"
            )
            validator = AlphaVantageAdapter.from_api_key(
                api_key,
                raw_root=raw_root,
                allow_full_history=True,
            )
            try:
                bars = tuple(
                    validator.get_daily_bars(
                        DailyBarRequest(
                            start=case.lifecycle_start_date,
                            end=case.anchor_date,
                            provider_symbols=(case.validator_symbol,),
                            adjustment=PriceRepresentation.RAW,
                            run_id=f"targeted-gap:{case.case_id}",
                        )
                    )
                )
            except AlphaVantageApiError as exc:
                fail_closed = True
                reports.append(
                    _provider_failure_report(
                        case,
                        expected_sessions=expected_sessions,
                        symbol_profile=symbol_profile,
                        error_type=type(exc).__name__,
                    )
                )
                continue

            result = evaluate_targeted_gap_validator(case, bars)
            if not result.ready_for_manual_adjudication:
                fail_closed = True
            reports.append(
                {
                    "case_id": case.case_id,
                    "symbol": case.symbol,
                    "exchange": case.exchange,
                    "lifecycle_start_date": case.lifecycle_start_date.isoformat(),
                    "observed_provider_id": case.observed_provider_id,
                    "observed_first_date": case.observed_first_date.isoformat(),
                    "observed_profile_receipt_id": symbol_profile.receipt_id,
                    "observed_profile_payload_sha256": symbol_profile.payload_checksum_sha256,
                    "calendar_definition_version": result.calendar_definition_version,
                    "expected_gap_sessions": [
                        day.isoformat() for day in result.expected_gap_sessions
                    ],
                    "validator_provider_id": case.validator_provider_id,
                    "validator_symbol": case.validator_symbol,
                    "validator_request_start": case.lifecycle_start_date.isoformat(),
                    "validator_request_end": case.anchor_date.isoformat(),
                    "validator_full_history_requested": True,
                    "validator_entitlement_assumed": False,
                    "validator_observed_session_count": result.validator_observed_session_count,
                    "validator_present_gap_sessions": [
                        day.isoformat() for day in result.validator_present_gap_sessions
                    ],
                    "validator_nonobserved_gap_sessions": [
                        day.isoformat() for day in result.validator_missing_gap_sessions
                    ],
                    "anchor_date": case.anchor_date.isoformat(),
                    "validator_anchor_present": result.validator_anchor_present,
                    "gap_fully_observed_by_validator": result.gap_fully_observed_by_validator,
                    "ready_for_manual_adjudication": result.ready_for_manual_adjudication,
                    "status": (
                        "VALIDATOR_PRESENT_READY_FOR_MANUAL_ADJUDICATION"
                        if result.ready_for_manual_adjudication
                        else "INCONCLUSIVE_VALIDATOR_NONOBSERVATION"
                    ),
                    "evidence_refs": list(case.evidence_refs),
                    "canonical_fill_allowed": False,
                    "price_rows_promoted": 0,
                    "bars_fabricated": 0,
                }
            )

        payload = {
            "schema_version": "tiingo-alpha-targeted-gap-validation-report-v0.1",
            "case_count": len(reports),
            "reports": reports,
            "provider_calls_made": True,
            "provider_acceptance_changed": False,
            "serving_selected": False,
            "canonical_dataset_written": False,
            "price_rows_promoted": 0,
            "bars_fabricated": 0,
        }
        report_path = (
            workspace.root
            / "evidence"
            / "targeted-gap-validation"
            / "tiingo-alpha-targeted-gap-validation-v0.1.json"
        )
        _persist_report(report_path, payload)
        output = dict(payload)
        output["report_path"] = str(report_path)
        print(json.dumps(output, indent=2, sort_keys=True))
        return 2 if fail_closed else 0
    except (
        OperatorWorkspaceError,
        TargetedGapValidationError,
        TiingoProfileError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ) as exc:
        print(f"targeted gap validation error: {exc}", file=sys.stderr)
        return 2


def _load_cases(path: Path) -> tuple[TargetedGapCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "cases"}:
        raise TargetedGapValidationError("targeted gap config has missing or unknown fields")
    if payload["schema_version"] != _SCHEMA_VERSION:
        raise TargetedGapValidationError("unsupported targeted gap config schema")
    raw_cases = payload["cases"]
    if not isinstance(raw_cases, list) or not raw_cases:
        raise TargetedGapValidationError("targeted gap config requires at least one case")

    expected_fields = {
        "case_id",
        "symbol",
        "exchange",
        "lifecycle_start_date",
        "observed_provider_id",
        "observed_first_date",
        "validator_provider_id",
        "validator_symbol",
        "anchor_date",
        "evidence_refs",
    }
    result: list[TargetedGapCase] = []
    seen_ids: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict) or set(raw) != expected_fields:
            raise TargetedGapValidationError("targeted gap case has missing or unknown fields")
        evidence_refs = raw["evidence_refs"]
        if not isinstance(evidence_refs, list) or not all(
            isinstance(item, str) and item.strip() for item in evidence_refs
        ):
            raise TargetedGapValidationError("targeted gap evidence_refs must be non-empty strings")
        case = TargetedGapCase(
            case_id=_text(raw["case_id"], "case_id"),
            symbol=_text(raw["symbol"], "symbol"),
            exchange=_text(raw["exchange"], "exchange"),
            lifecycle_start_date=date.fromisoformat(
                _text(raw["lifecycle_start_date"], "lifecycle_start_date")
            ),
            observed_provider_id=_text(raw["observed_provider_id"], "observed_provider_id"),
            observed_first_date=date.fromisoformat(
                _text(raw["observed_first_date"], "observed_first_date")
            ),
            validator_provider_id=_text(raw["validator_provider_id"], "validator_provider_id"),
            validator_symbol=_text(raw["validator_symbol"], "validator_symbol"),
            anchor_date=date.fromisoformat(_text(raw["anchor_date"], "anchor_date")),
            evidence_refs=tuple(evidence_refs),
        )
        if case.case_id in seen_ids:
            raise TargetedGapValidationError(f"duplicate targeted gap case ID: {case.case_id}")
        seen_ids.add(case.case_id)
        result.append(case)
    return tuple(result)


def _provider_failure_report(
    case: TargetedGapCase,
    *,
    expected_sessions: tuple[date, ...],
    symbol_profile: object,
    error_type: str,
) -> dict[str, object]:
    receipt_id = getattr(symbol_profile, "receipt_id", None)
    payload_checksum = getattr(symbol_profile, "payload_checksum_sha256", None)
    return {
        "case_id": case.case_id,
        "symbol": case.symbol,
        "exchange": case.exchange,
        "lifecycle_start_date": case.lifecycle_start_date.isoformat(),
        "observed_provider_id": case.observed_provider_id,
        "observed_first_date": case.observed_first_date.isoformat(),
        "observed_profile_receipt_id": receipt_id,
        "observed_profile_payload_sha256": payload_checksum,
        "expected_gap_sessions": [day.isoformat() for day in expected_sessions],
        "validator_provider_id": case.validator_provider_id,
        "validator_symbol": case.validator_symbol,
        "validator_full_history_requested": True,
        "validator_entitlement_assumed": False,
        "status": "INCONCLUSIVE_PROVIDER_FAILURE",
        "provider_error_type": error_type,
        "ready_for_manual_adjudication": False,
        "canonical_fill_allowed": False,
        "price_rows_promoted": 0,
        "bars_fabricated": 0,
        "evidence_refs": list(case.evidence_refs),
    }


def _persist_report(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TargetedGapValidationError(f"{field} must be a non-empty string")
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
