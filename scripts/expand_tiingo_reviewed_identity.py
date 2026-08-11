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
    "A": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AAPL": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "ABBV": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ABNB": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AIZ": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AKAM": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ALLE": "WHEN_ISSUED_START_MATCH",
    "AMD": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "AMP": "WHEN_ISSUED_START_MATCH",
    "AMZN": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ANET": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "APP": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "APTV": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "AVGO": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AWK": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AXON": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "CAT": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "CRM": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
}
_NEW_REVIEWED_SYMBOLS = frozenset({"AAPL", "ABBV", "AMD", "AVGO", "CAT", "CRM"})
_DEFERRED_REASONS = {
    "ALGN": (
        "Tiingo begins 2001-01-30 after the sourced public-trading start 2001-01-26; "
        "canonical promotion remains blocked until the missing sessions are independently resolved."
    ),
    "BAC": (
        "The Tiingo BAC series begins before the 1998 NationsBank/BankAmerica merger, while "
        "the current issuer is the successor to NationsBank; permanent-issuer ownership of the "
        "pre-merger provider history remains unresolved."
    ),
    "BKNG": (
        "Tiingo begins 1999-03-31 after the sourced Priceline public-trading start 1999-03-29; "
        "canonical promotion remains blocked until the missing initial sessions are resolved."
    ),
    "COST": (
        "Tiingo COST begins in 1996, while Costco's official history records the PriceCostco "
        "ticker PCCW before a February 1997 change to COST; the exact effective trading date "
        "needed for explicit symbol history remains unresolved."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    cases_path = repository_root / "configs" / "tiingo_symbol_lineage_cases_v0.5.json"
    seeds_path = repository_root / "configs" / "tiingo_reviewed_identity_seeds_v0.6.json"

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
            missing = sorted(
                item.source_symbol
                for item in audit.observations
                if item.observed_first_date is None
            )
            raise OperatorWorkspaceError(
                "one or more reviewed expansion symbols are absent from the durable Tiingo "
                f"profile: {missing}"
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
                "new_reviewed_symbols": sorted(_NEW_REVIEWED_SYMBOLS),
                "deferred_symbols": sorted(_DEFERRED_REASONS),
                "deferred_reasons": _DEFERRED_REASONS,
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
