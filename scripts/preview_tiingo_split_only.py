"""Build a private split-only normalization preview from durable Tiingo evidence."""

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
from trade_scout.data.providers.tiingo_split_preview import (
    TiingoSplitPreviewError,
    persist_tiingo_split_only_preview,
    preview_durable_tiingo_split_only,
)


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
                "durable evidence is inconsistent; split-only preview is blocked fail-closed"
            )

        candidate_path = (
            workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        )
        if not candidate_path.is_file():
            raise OperatorWorkspaceError(
                "reviewed Tiingo identity candidate is missing; build and promote identity first"
            )

        preview = preview_durable_tiingo_split_only(
            receipt_root=workspace.tiingo_receipts_root,
            raw_root=workspace.tiingo_raw_root,
            storage_namespace=workspace.manifest.storage_namespace,
            candidate_path=candidate_path,
            canonical_root=workspace.canonical_root,
        )
        output = (
            workspace.root / "evidence" / "split-normalization" / "tiingo-reviewed-preview.json"
        )
        persist_tiingo_split_only_preview(output, preview)
    except (OperatorWorkspaceError, TiingoSplitPreviewError) as exc:
        print(f"Tiingo split-only preview error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "preview_path": str(output),
                "snapshot_version": preview.snapshot_version,
                "symbol_count": preview.symbol_count,
                "row_count": preview.row_count,
                "split_event_count": preview.split_event_count,
                "dividend_event_count": preview.dividend_event_count,
                "cross_check_eligible_symbol_count": preview.cross_check_eligible_symbol_count,
                "cross_check_mismatch_field_count": preview.cross_check_mismatch_field_count,
                "normalization_issue_count": preview.normalization_issue_count,
                "quality_issue_count": preview.quality_issue_count,
                "validation_passed": preview.validation_passed,
                "price_rows_promoted": preview.price_rows_promoted,
                "symbols": [
                    {
                        "query_symbol": item.query_symbol,
                        "row_count": item.row_count,
                        "split_event_count": item.split_event_count,
                        "dividend_event_count": item.dividend_event_count,
                        "cross_check_eligible": item.tiingo_adjusted_cross_check_eligible,
                        "cross_check_mismatch_count": (
                            item.tiingo_adjusted_cross_check_mismatch_count
                        ),
                        "normalization_status": str(item.normalization_status),
                    }
                    for item in preview.symbols
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if preview.validation_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
