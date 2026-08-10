"""Promote the bounded reviewed Tiingo price slice into immutable canonical storage."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.contracts import DatasetVersion
from trade_scout.data.providers.tiingo_canonical_promotion import (
    TiingoCanonicalPromotionError,
    persist_tiingo_canonical_promotion_report,
    promote_reviewed_tiingo_prices,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    load_reviewed_identity_snapshot_candidate,
)

_V04_IDENTITY_SNAPSHOT = "tiingo-reviewed-identity-candidate-v0.4"
_V04_DATASET_VERSION = DatasetVersion("tiingo-reviewed-split-only-v0.3")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable evidence is inconsistent; canonical price promotion is blocked fail-closed"
            )

        candidate_path = (
            workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        )
        if not candidate_path.is_file():
            raise OperatorWorkspaceError(
                "reviewed Tiingo identity candidate is missing; build and promote identity first"
            )
        candidate = load_reviewed_identity_snapshot_candidate(candidate_path)
        dataset_version = (
            _V04_DATASET_VERSION
            if candidate.snapshot_version == _V04_IDENTITY_SNAPSHOT
            else None
        )

        result = promote_reviewed_tiingo_prices(
            receipt_root=workspace.tiingo_receipts_root,
            raw_root=workspace.tiingo_raw_root,
            storage_namespace=workspace.manifest.storage_namespace,
            candidate_path=candidate_path,
            canonical_root=workspace.canonical_root,
            dataset_version=dataset_version,
        )
        output = (
            workspace.root
            / "evidence"
            / "canonical-promotion"
            / f"{result.manifest.dataset_version}.json"
        )
        persist_tiingo_canonical_promotion_report(output, result)
    except (
        OperatorWorkspaceError,
        ReviewedIdentitySnapshotError,
        TiingoCanonicalPromotionError,
    ) as exc:
        print(f"Tiingo canonical price promotion error: {exc}", file=sys.stderr)
        return 2

    manifest = result.manifest
    print(
        json.dumps(
            {
                "report_path": str(output),
                "dataset_id": manifest.dataset_id,
                "dataset_version": str(manifest.dataset_version),
                "identity_snapshot_version": result.identity_snapshot_version,
                "promotion_scope": result.promotion_scope,
                "already_registered": result.already_registered,
                "symbol_count": result.symbol_count,
                "record_count": result.row_count,
                "first_trade_date": manifest.first_trade_date.isoformat(),
                "last_trade_date": manifest.last_trade_date.isoformat(),
                "split_event_count": result.split_event_count,
                "dividend_event_count": result.dividend_event_count,
                "cross_check_eligible_symbol_count": result.cross_check_eligible_symbol_count,
                "cross_check_mismatch_field_count": result.cross_check_mismatch_field_count,
                "session_calendar_definition_version": (result.session_calendar_definition_version),
                "missing_expected_session_count": result.missing_expected_session_count,
                "unexpected_observed_date_count": result.unexpected_observed_date_count,
                "duplicate_observed_date_count": result.duplicate_observed_date_count,
                "session_completeness_passed": True,
                "pass_count": manifest.quality_summary.pass_count,
                "warn_count": manifest.quality_summary.warn_count,
                "quarantine_count": manifest.quality_summary.quarantine_count,
                "reject_count": manifest.quality_summary.reject_count,
                "content_checksum_sha256": manifest.content_checksum_sha256,
                "parquet_checksum_sha256": manifest.parquet_checksum_sha256,
                "parquet_path": str(workspace.canonical_root / manifest.parquet_relative_path),
                "provider_acceptance_changed": False,
                "serving_selected": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
