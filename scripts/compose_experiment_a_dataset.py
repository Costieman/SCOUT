"""Attach a separately canonicalized benchmark to a reviewed research cohort."""

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
from trade_scout.data.canonical_composition import (
    CanonicalCompositionError,
    compose_canonical_datasets,
)
from trade_scout.data.canonical_storage import CanonicalDailyBarStore
from trade_scout.data.contracts import DatasetVersion


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compose an immutable reviewed-cohort dataset with a separately canonicalized benchmark."
        )
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--research-dataset-version",
        default=None,
        help="Research cohort dataset; defaults to workspace.json canonical_dataset_version.",
    )
    parser.add_argument("--benchmark-dataset-version", required=True)
    parser.add_argument("--target-dataset-version", required=True)
    parser.add_argument(
        "--target-dataset-id",
        default="experiment-a-reviewed-cohort-plus-benchmark",
    )
    parser.add_argument(
        "--universe-version",
        default="reviewed-canonical-fixed-cohort-plus-benchmark-v0.1",
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
                "durable workspace evidence is inconsistent; composition is blocked fail-closed"
            )

        research_text = (
            args.research_dataset_version or workspace.manifest.canonical_dataset_version
        )
        if research_text is None:
            raise OperatorWorkspaceError(
                "no research canonical dataset is selected; pass --research-dataset-version "
                "or select one in workspace.json"
            )

        store = CanonicalDailyBarStore(workspace.canonical_root)
        result = compose_canonical_datasets(
            store,
            source_dataset_versions=(
                DatasetVersion(research_text),
                DatasetVersion(args.benchmark_dataset_version),
            ),
            target_dataset_id=args.target_dataset_id,
            target_dataset_version=DatasetVersion(args.target_dataset_version),
            created_at=datetime.now(UTC),
            universe_construction_version=args.universe_version,
        )
    except (OperatorWorkspaceError, CanonicalCompositionError, ValueError) as exc:
        print(f"canonical composition error: {exc}", file=sys.stderr)
        return 2

    manifest = result.manifest
    print(
        json.dumps(
            {
                "dataset_id": manifest.dataset_id,
                "dataset_version": str(manifest.dataset_version),
                "source_dataset_versions": [str(value) for value in result.source_dataset_versions],
                "record_count": manifest.record_count,
                "first_trade_date": manifest.first_trade_date.isoformat(),
                "last_trade_date": manifest.last_trade_date.isoformat(),
                "content_checksum_sha256": manifest.content_checksum_sha256,
                "primary_provider_id": manifest.primary_provider_id,
                "adjustment_policy_version": manifest.adjustment_policy_version,
                "universe_construction_version": manifest.universe_construction_version,
                "source_datasets_modified": False,
                "provider_calls_made": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
