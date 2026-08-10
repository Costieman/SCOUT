"""Build the first private Phase 2 feature snapshot from canonical daily bars."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from trade_scout.app.operator_workspace import (
    OperatorWorkspaceError,
    load_operator_workspace,
    validate_workspace_location,
    verify_operator_workspace,
)
from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetNotFoundError,
)
from trade_scout.data.contracts import DatasetVersion
from trade_scout.features.contracts import FeatureAvailabilityStatus
from trade_scout.features.initial import (
    INITIAL_FEATURE_SET,
    FeatureInputError,
    compute_initial_feature_frame,
    initial_feature_definition_sha256,
)
from trade_scout.features.storage import (
    FeatureSnapshotManifest,
    FeatureSnapshotPromotionRequest,
    FeatureSnapshotStore,
)

_SOURCE_DATASET_VERSION = DatasetVersion("tiingo-reviewed-split-only-v0.1")
_RESEARCH_SCOPE = "reviewed_seed_set_only"


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
                "durable workspace evidence is inconsistent; feature build is blocked fail-closed"
            )

        canonical_store = CanonicalDailyBarStore(workspace.canonical_root)
        source_manifest = canonical_store.get_manifest(_SOURCE_DATASET_VERSION)
        if source_manifest is None:
            raise OperatorWorkspaceError(
                "reviewed canonical price slice is missing; promote reviewed prices first"
            )
        if (
            source_manifest.quality_summary.warn_count
            or source_manifest.quality_summary.quarantine_count
            or source_manifest.quality_summary.reject_count
        ):
            raise OperatorWorkspaceError(
                "reviewed canonical price slice contains non-PASS quality states"
            )

        bars = canonical_store.load(_SOURCE_DATASET_VERSION)
        values = compute_initial_feature_frame(bars)
        feature_store = FeatureSnapshotStore(workspace.canonical_root)
        existing = feature_store.get_manifest(
            _SOURCE_DATASET_VERSION,
            INITIAL_FEATURE_SET.feature_set_version,
        )
        created_at = existing.created_at if existing is not None else datetime.now(UTC)
        request = FeatureSnapshotPromotionRequest(
            dataset_version=_SOURCE_DATASET_VERSION,
            feature_set_version=INITIAL_FEATURE_SET.feature_set_version,
            created_at=created_at,
            source_canonical_content_sha256=source_manifest.content_checksum_sha256,
            feature_definition_sha256=initial_feature_definition_sha256(),
        )
        manifest = feature_store.promote(values, request)
        loaded = feature_store.load(
            _SOURCE_DATASET_VERSION,
            INITIAL_FEATURE_SET.feature_set_version,
        )
        if loaded != values:
            raise OperatorWorkspaceError(
                "feature snapshot reload does not exactly match the deterministic feature build"
            )

        report_path = (
            workspace.root
            / "evidence"
            / "feature-foundation"
            / f"{INITIAL_FEATURE_SET.feature_set_version}.json"
        )
        _persist_report(report_path, manifest, already_registered=existing is not None)
    except (
        OperatorWorkspaceError,
        CanonicalDatasetNotFoundError,
        FeatureInputError,
    ) as exc:
        print(f"initial feature build error: {exc}", file=sys.stderr)
        return 2

    by_feature: dict[str, dict[str, int]] = {}
    for value in values:
        counts = by_feature.setdefault(
            value.feature_name,
            {status.value: 0 for status in FeatureAvailabilityStatus},
        )
        counts[value.availability_status.value] += 1

    print(
        json.dumps(
            {
                "report_path": str(report_path),
                "dataset_version": str(manifest.dataset_version),
                "feature_set_version": manifest.feature_set_version,
                "research_scope": _RESEARCH_SCOPE,
                "already_registered": existing is not None,
                "feature_definition_sha256": manifest.feature_definition_sha256,
                "source_canonical_content_sha256": (manifest.source_canonical_content_sha256),
                "record_count": manifest.record_count,
                "available_count": manifest.available_count,
                "warmup_count": manifest.warmup_count,
                "input_unavailable_count": manifest.input_unavailable_count,
                "first_trade_date": manifest.first_trade_date.isoformat(),
                "last_trade_date": manifest.last_trade_date.isoformat(),
                "content_checksum_sha256": manifest.content_checksum_sha256,
                "parquet_checksum_sha256": manifest.parquet_checksum_sha256,
                "parquet_path": str(workspace.canonical_root / manifest.parquet_relative_path),
                "feature_counts": by_feature,
                "provider_calls_made": False,
                "serving_selected": False,
                "pattern_engine_ready": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _persist_report(
    path: Path,
    manifest: FeatureSnapshotManifest,
    *,
    already_registered: bool,
) -> None:
    payload = {
        "schema_version": "phase2-initial-feature-foundation-report-v0.1",
        "dataset_version": str(manifest.dataset_version),
        "feature_set_version": manifest.feature_set_version,
        "research_scope": _RESEARCH_SCOPE,
        "already_registered": already_registered,
        "source_canonical_content_sha256": manifest.source_canonical_content_sha256,
        "feature_definition_sha256": manifest.feature_definition_sha256,
        "record_count": manifest.record_count,
        "available_count": manifest.available_count,
        "warmup_count": manifest.warmup_count,
        "input_unavailable_count": manifest.input_unavailable_count,
        "first_trade_date": manifest.first_trade_date.isoformat(),
        "last_trade_date": manifest.last_trade_date.isoformat(),
        "content_checksum_sha256": manifest.content_checksum_sha256,
        "parquet_checksum_sha256": manifest.parquet_checksum_sha256,
        "parquet_relative_path": manifest.parquet_relative_path,
        "provider_calls_made": False,
        "serving_selected": False,
        "pattern_engine_ready": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())
