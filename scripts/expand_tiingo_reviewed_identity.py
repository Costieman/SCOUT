"""Expand the private reviewed Tiingo identity candidate to the next sourced seed batch."""

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
from trade_scout.data.providers.tiingo_lineage_audit import (
    TiingoLineageAuditError,
    audit_tiingo_profile_lineage,
    load_lineage_cases,
    persist_tiingo_lineage_audit,
)
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    build_reviewed_identity_snapshot_candidate,
    load_reviewed_identity_seed_set,
    persist_reviewed_identity_snapshot_candidate,
)

_EXPECTED_CLASSIFICATIONS = {
    "ABNB": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ALLE": "WHEN_ISSUED_START_MATCH",
    "ANET": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "APP": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "APTV": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "AWK": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AXON": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    cases_path = repository_root / "configs" / "tiingo_symbol_lineage_cases_v0.2.json"
    seeds_path = repository_root / "configs" / "tiingo_reviewed_identity_seeds_v0.3.json"

    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable evidence is inconsistent; reviewed identity expansion is blocked "
                "fail-closed"
            )

        profile_path = workspace.root / "evidence" / "tiingo-profile" / "profile.json"
        if not profile_path.is_file():
            raise OperatorWorkspaceError("Tiingo profile is missing; run profile-tiingo first")

        cases = load_lineage_cases(cases_path)
        audit = audit_tiingo_profile_lineage(profile_path=profile_path, cases=cases)
        if audit.profiled_case_count != audit.case_count:
            raise OperatorWorkspaceError(
                "one or more reviewed expansion symbols are absent from the durable Tiingo profile"
            )

        classifications = {item.source_symbol: item.classification for item in audit.observations}
        if classifications != _EXPECTED_CLASSIFICATIONS:
            raise OperatorWorkspaceError(
                "observed Tiingo lineage starts differ from the reviewed expansion expectations: "
                f"{json.dumps(classifications, sort_keys=True)}"
            )

        audit_path = workspace.root / "evidence" / "tiingo-lineage" / "audit.json"
        persist_tiingo_lineage_audit(audit_path, audit)

        seed_set = load_reviewed_identity_seed_set(seeds_path)
        candidate = build_reviewed_identity_snapshot_candidate(
            seed_set=seed_set,
            lineage_audit_path=audit_path,
        )
        if not candidate.promotion_ready:
            raise OperatorWorkspaceError(
                "expanded reviewed identity candidate still contains dated coverage gaps"
            )

        candidate_path = (
            workspace.root / "evidence" / "instrument-identity" / "tiingo-reviewed-candidate.json"
        )
        persist_reviewed_identity_snapshot_candidate(candidate_path, candidate)
    except (
        OperatorWorkspaceError,
        TiingoLineageAuditError,
        ReviewedIdentitySnapshotError,
    ) as exc:
        print(f"reviewed Tiingo identity expansion error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "audit_path": str(audit_path),
                "candidate_path": str(candidate_path),
                "snapshot_version": candidate.snapshot_version,
                "instrument_count": len(candidate.instruments),
                "symbol_history_count": len(candidate.symbol_history),
                "provider_series_link_count": len(candidate.provider_series_links),
                "coverage_gap_count": len(candidate.coverage_gaps),
                "promotion_ready": candidate.promotion_ready,
                "reviewed_symbols": sorted(classifications),
                "classification_counts": {
                    classification: sum(
                        value == classification for value in classifications.values()
                    )
                    for classification in sorted(set(classifications.values()))
                },
                "provider_calls_made": False,
                "price_rows_promoted": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
