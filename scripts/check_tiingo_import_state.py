"""Audit one local Tiingo import workspace without mutating provider or canonical state.

The checker is deliberately read-only. It reconciles durable receipts, structural profile,
identity decisions, registered instrument master, selected canonical dataset, and (optionally)
re-runs split-only transformation diagnostics. It makes no provider calls.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetIntegrityError,
    CanonicalDatasetNotFoundError,
)
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.instrument_storage import (
    InstrumentMasterIntegrityError,
    InstrumentMasterNotFoundError,
    InstrumentMasterStore,
)
from trade_scout.data.providers.tiingo_split_preview import (
    TiingoSplitPreviewError,
    preview_durable_tiingo_split_only,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_snapshot_candidate,
)

_STRUCTURAL_FIELDS = (
    "invalid_date_row_count",
    "duplicate_date_count",
    "non_monotonic_date_count",
    "missing_required_field_row_count",
    "invalid_numeric_row_count",
    "ohlc_invariant_violation_count",
    "negative_volume_count",
    "long_calendar_gap_count",
)


class ImportStateCheckError(RuntimeError):
    """Raised when checker input itself is malformed or unavailable."""


@dataclass(frozen=True, slots=True)
class CheckResult:
    check: str
    status: str
    message: str
    details: dict[str, object]


class Reporter:
    def __init__(self) -> None:
        self.results: list[CheckResult] = []

    def add(
        self,
        check: str,
        status: str,
        message: str,
        **details: object,
    ) -> None:
        self.results.append(
            CheckResult(check=check, status=status, message=message, details=dict(details))
        )
        suffix = "" if not details else " " + json.dumps(details, sort_keys=True, default=str)
        print(f"[{status}] {check}: {message}{suffix}", flush=True)

    @property
    def failed(self) -> bool:
        return any(item.status == "FAIL" for item in self.results)

    @property
    def warned(self) -> bool:
        return any(item.status == "WARN" for item in self.results)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only end-to-end checker for the current Tiingo import state."
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--deep",
        action="store_true",
        help="Re-run all promoted-symbol split-only/normalization diagnostics; can be slow.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Optional path for the complete machine-readable report.",
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    reporter = Reporter()

    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
    except OperatorWorkspaceError as exc:
        print(f"import state checker error: {exc}", file=sys.stderr)
        return 2

    report: dict[str, object] = {
        "schema_version": "trade-scout-tiingo-import-state-check-v0.1",
        "workspace_root": str(root),
        "deep": bool(args.deep),
    }

    # 1. Durable workspace / receipt integrity.
    try:
        verification = verify_operator_workspace(workspace)
    except OperatorWorkspaceError as exc:
        reporter.add("workspace", "FAIL", str(exc))
    else:
        reporter.add(
            "workspace",
            "PASS" if verification.is_consistent else "FAIL",
            "durable workspace is internally consistent"
            if verification.is_consistent
            else "durable workspace has receipt/state inconsistencies",
            durable_completed_symbol_count=verification.durable_completed_symbol_count,
            receipt_file_count=verification.receipt_file_count,
            verified_receipt_count=verification.verified_receipt_count,
            missing_receipt_symbols=list(verification.missing_receipt_symbols),
            receipt_subjects_not_in_state=list(verification.receipt_subjects_not_in_state),
            invalid_receipt_paths=list(verification.invalid_receipt_paths),
        )

    # 2. Structural profile.
    profile_path = root / "evidence" / "tiingo-profile" / "profile.json"
    profile_symbols: dict[str, dict[str, object]] = {}
    if not profile_path.is_file():
        reporter.add("structural_profile", "FAIL", "Tiingo profile is missing", path=str(profile_path))
    else:
        try:
            profile_payload = _load_json_object(profile_path)
            rows = profile_payload.get("symbols")
            if not isinstance(rows, list):
                raise ImportStateCheckError("profile symbols must be an array")
            for row in rows:
                if not isinstance(row, dict):
                    raise ImportStateCheckError("profile contains a malformed symbol row")
                symbol = _text(row.get("source_symbol"), "source_symbol").upper()
                if symbol in profile_symbols:
                    raise ImportStateCheckError(f"duplicate profile symbol {symbol}")
                profile_symbols[symbol] = row
            anomalous = sorted(
                symbol
                for symbol, row in profile_symbols.items()
                if sum(_non_negative_int(row.get(field), f"{symbol}.{field}") for field in _STRUCTURAL_FIELDS)
                > 0
            )
            reporter.add(
                "structural_profile",
                "WARN" if anomalous else "PASS",
                "profile loaded; anomalous symbols remain quarantinable"
                if anomalous
                else "all profiled symbols are structurally clean",
                symbol_count=len(profile_symbols),
                anomalous_symbol_count=len(anomalous),
                anomalous_symbols=anomalous,
                total_row_count=profile_payload.get("total_row_count"),
            )
            report["structural_profile_path"] = str(profile_path)
        except (OSError, json.JSONDecodeError, ImportStateCheckError) as exc:
            reporter.add("structural_profile", "FAIL", str(exc), path=str(profile_path))

    # 3. Identity decision/checkpoint reconciliation.
    overnight_root = root / "evidence" / "overnight-import"
    checkpoint_path = overnight_root / "identity-checkpoint.json"
    ready_path = overnight_root / "ready.json"
    deferred_path = overnight_root / "deferred.json"
    checkpoint = _load_evidence_file(checkpoint_path, reporter, "identity_checkpoint")
    ready = _load_evidence_file(ready_path, reporter, "identity_ready")
    deferred = _load_evidence_file(deferred_path, reporter, "identity_deferred")

    checkpoint_symbols = {_evidence_symbol(item) for item in checkpoint}
    ready_symbols = {_evidence_symbol(item) for item in ready}
    deferred_symbols = {_evidence_symbol(item) for item in deferred}
    overlap = sorted(ready_symbols & deferred_symbols)
    unclassified = sorted(checkpoint_symbols - ready_symbols - deferred_symbols)
    missing_checkpoint = sorted((ready_symbols | deferred_symbols) - checkpoint_symbols)
    reason_counts = Counter(
        _text(item.get("evidence_kind"), "evidence_kind") for item in deferred
    )
    identity_status = "PASS" if not overlap and not unclassified and not missing_checkpoint else "FAIL"
    reporter.add(
        "identity_reconciliation",
        identity_status,
        "checkpoint terminal decisions reconcile"
        if identity_status == "PASS"
        else "identity checkpoint and terminal decision files do not reconcile",
        checkpoint_count=len(checkpoint_symbols),
        ready_count=len(ready_symbols),
        deferred_count=len(deferred_symbols),
        overlap=overlap,
        unclassified=unclassified,
        missing_checkpoint=missing_checkpoint,
        deferred_reason_counts=dict(sorted(reason_counts.items())),
    )

    # 4. Reviewed candidate and provider link uniqueness / receipt coverage.
    candidate_path = root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
    candidate = None
    if not candidate_path.is_file():
        reporter.add("reviewed_candidate", "FAIL", "current reviewed candidate is missing")
    else:
        try:
            candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
            query_symbols = [
                link.query_symbol.upper()
                for link in candidate.provider_series_links
                if link.provider_id == "tiingo"
            ]
            duplicate_queries = sorted(
                symbol for symbol, count in Counter(query_symbols).items() if count > 1
            )
            instrument_ids = [str(item.instrument_id) for item in candidate.instruments]
            duplicate_ids = sorted(
                item for item, count in Counter(instrument_ids).items() if count > 1
            )
            receipt_counts = {
                symbol: len(tuple((workspace.tiingo_receipts_root / symbol).glob("*.json")))
                for symbol in query_symbols
            }
            missing_receipts = sorted(symbol for symbol, count in receipt_counts.items() if count == 0)
            duplicate_receipts = sorted(symbol for symbol, count in receipt_counts.items() if count > 1)
            candidate_ok = (
                candidate.promotion_ready
                and not duplicate_queries
                and not duplicate_ids
                and not missing_receipts
                and not duplicate_receipts
            )
            reporter.add(
                "reviewed_candidate",
                "PASS" if candidate_ok else "FAIL",
                "reviewed candidate is promotion-ready and has one durable receipt per Tiingo link"
                if candidate_ok
                else "reviewed candidate failed identity/link/receipt checks",
                snapshot_version=candidate.snapshot_version,
                instrument_count=len(candidate.instruments),
                tiingo_link_count=len(query_symbols),
                coverage_gap_count=len(candidate.coverage_gaps),
                duplicate_query_symbols=duplicate_queries,
                duplicate_instrument_ids=duplicate_ids,
                missing_receipts=missing_receipts,
                duplicate_receipts=duplicate_receipts,
            )
            report["candidate_path"] = str(candidate_path)
        except ReviewedIdentitySnapshotError as exc:
            reporter.add("reviewed_candidate", "FAIL", str(exc), path=str(candidate_path))

    # 5. Instrument master registration and equality.
    if candidate is not None:
        store = InstrumentMasterStore(workspace.canonical_root)
        try:
            manifest = store.get_manifest(candidate.snapshot_version)
            snapshot = store.load(candidate.snapshot_version)
            exact = (
                snapshot.instruments == candidate.instruments
                and snapshot.symbol_history == candidate.symbol_history
            )
            reporter.add(
                "instrument_master",
                "PASS" if exact else "FAIL",
                "registered instrument master exactly matches reviewed candidate"
                if exact
                else "registered instrument master differs from reviewed candidate",
                snapshot_version=manifest.snapshot_version,
                instrument_count=manifest.instrument_count,
                symbol_history_count=manifest.symbol_history_count,
                instrument_logical_sha256=manifest.instrument_logical_sha256,
                symbol_history_logical_sha256=manifest.symbol_history_logical_sha256,
            )
        except (InstrumentMasterNotFoundError, InstrumentMasterIntegrityError) as exc:
            reporter.add("instrument_master", "FAIL", str(exc))

    # 6. Selected canonical dataset integrity and identity coverage.
    selected_version = workspace.manifest.canonical_dataset_version
    report["selected_canonical_dataset_version"] = selected_version
    if selected_version is None:
        reporter.add("canonical_dataset", "FAIL", "workspace has no selected canonical dataset")
    else:
        canonical = CanonicalDailyBarStore(workspace.canonical_root)
        try:
            manifest = canonical.get_manifest(DatasetVersion(selected_version))
            if manifest is None:
                raise CanonicalDatasetNotFoundError(selected_version)
            bars = canonical.load(DatasetVersion(selected_version))
            instrument_ids = {str(item.instrument_id) for item in bars}
            candidate_ids = (
                {str(item.instrument_id) for item in candidate.instruments}
                if candidate is not None
                else set()
            )
            unknown = sorted(instrument_ids - candidate_ids) if candidate_ids else []
            missing = sorted(candidate_ids - instrument_ids) if candidate_ids else []
            quality = manifest.quality_summary
            canonical_ok = (
                len(bars) == manifest.record_count
                and quality.quarantine_count == 0
                and quality.reject_count == 0
                and not unknown
                and not missing
            )
            reporter.add(
                "canonical_dataset",
                "PASS" if canonical_ok else "FAIL",
                "selected canonical dataset passed checksum/load/identity reconciliation"
                if canonical_ok
                else "selected canonical dataset failed reconciliation",
                dataset_version=str(manifest.dataset_version),
                record_count=manifest.record_count,
                instrument_count=len(instrument_ids),
                first_trade_date=manifest.first_trade_date.isoformat(),
                last_trade_date=manifest.last_trade_date.isoformat(),
                pass_count=quality.pass_count,
                warn_count=quality.warn_count,
                quarantine_count=quality.quarantine_count,
                reject_count=quality.reject_count,
                unknown_canonical_instrument_ids=unknown,
                candidate_instruments_missing_from_canonical=missing,
            )
        except (
            CanonicalDatasetIntegrityError,
            CanonicalDatasetNotFoundError,
            OSError,
            KeyError,
        ) as exc:
            reporter.add("canonical_dataset", "FAIL", str(exc))

    # 7. Optional deep provider-transform/normalization audit.
    if args.deep and candidate is not None:
        try:
            preview = preview_durable_tiingo_split_only(
                receipt_root=workspace.tiingo_receipts_root,
                raw_root=workspace.tiingo_raw_root,
                storage_namespace=workspace.manifest.storage_namespace,
                candidate_path=candidate_path,
                canonical_root=workspace.canonical_root,
            )
            failing_symbols = sorted(
                item.query_symbol
                for item in preview.symbols
                if (
                    item.tiingo_adjusted_cross_check_mismatch_count
                    or item.normalization_issue_count
                    or item.quality_issue_count
                )
            )
            reporter.add(
                "deep_price_transform",
                "PASS" if preview.validation_passed else "FAIL",
                "all promoted-symbol transformation diagnostics pass"
                if preview.validation_passed
                else "one or more promoted symbols fail transformation diagnostics",
                symbol_count=preview.symbol_count,
                row_count=preview.row_count,
                split_event_count=preview.split_event_count,
                dividend_event_count=preview.dividend_event_count,
                cross_check_eligible_symbol_count=preview.cross_check_eligible_symbol_count,
                cross_check_mismatch_field_count=preview.cross_check_mismatch_field_count,
                normalization_issue_count=preview.normalization_issue_count,
                quality_issue_count=preview.quality_issue_count,
                failing_symbols=failing_symbols,
            )
        except TiingoSplitPreviewError as exc:
            reporter.add("deep_price_transform", "FAIL", str(exc))
    elif candidate is not None:
        reporter.add(
            "deep_price_transform",
            "SKIP",
            "deep price transformation audit not requested; pass --deep to run it",
        )

    # 8. High-level universe accounting.
    if profile_symbols and candidate is not None:
        reviewed_symbols = {
            link.query_symbol.upper()
            for link in candidate.provider_series_links
            if link.provider_id == "tiingo"
        }
        unresolved_profile = sorted(set(profile_symbols) - reviewed_symbols)
        terminal_overlap = sorted(set(unresolved_profile) & reviewed_symbols)
        reporter.add(
            "universe_accounting",
            "PASS" if not terminal_overlap else "FAIL",
            "profile universe reconciled against current reviewed scope",
            profile_symbol_count=len(profile_symbols),
            reviewed_symbol_count=len(reviewed_symbols),
            unresolved_profile_symbol_count=len(unresolved_profile),
            unresolved_profile_symbols=unresolved_profile,
        )

    counts = Counter(item.status for item in reporter.results)
    overall = "FAIL" if reporter.failed else "WARN" if reporter.warned else "PASS"
    report["overall_status"] = overall
    report["check_status_counts"] = dict(sorted(counts.items()))
    report["checks"] = [asdict(item) for item in reporter.results]

    print("", flush=True)
    print("=========================================", flush=True)
    print(f"IMPORT STATE CHECK: {overall}", flush=True)
    print(
        f"PASS={counts.get('PASS', 0)} WARN={counts.get('WARN', 0)} "
        f"FAIL={counts.get('FAIL', 0)} SKIP={counts.get('SKIP', 0)}",
        flush=True,
    )
    print("=========================================", flush=True)

    if args.json_out is not None:
        target = args.json_out.expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(target)
        print(f"report: {target}", flush=True)

    return 2 if overall == "FAIL" else 0


def _load_evidence_file(
    path: Path,
    reporter: Reporter,
    check: str,
) -> list[dict[str, object]]:
    if not path.is_file():
        reporter.add(check, "WARN", "evidence file is absent", path=str(path))
        return []
    try:
        payload = _load_json_object(path)
        rows = payload.get("evidence")
        if not isinstance(rows, list):
            raise ImportStateCheckError("evidence must be an array")
        result: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ImportStateCheckError("evidence contains malformed row")
            result.append(row)
        reporter.add(check, "PASS", "evidence file loaded", path=str(path), count=len(result))
        return result
    except (OSError, json.JSONDecodeError, ImportStateCheckError) as exc:
        reporter.add(check, "FAIL", str(exc), path=str(path))
        return []


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ImportStateCheckError(f"{path} root must be an object")
    return payload


def _evidence_symbol(item: dict[str, object]) -> str:
    return _text(item.get("source_symbol"), "source_symbol").upper()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ImportStateCheckError(f"{field} must be non-empty text")
    return value.strip()


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ImportStateCheckError(f"{field} must be a non-negative integer")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
