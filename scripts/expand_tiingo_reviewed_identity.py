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
    persist_tiingo_lineage_audit,
)
from trade_scout.data.providers.tiingo_lineage_case_source import load_lineage_case_source
from trade_scout.data.reviewed_identity_seed_source import load_reviewed_identity_seed_source
from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    build_reviewed_identity_snapshot_candidate,
    persist_reviewed_identity_snapshot_candidate,
)

_EXPECTED_CLASSIFICATIONS = {
    "A": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AAPL": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "ABBV": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ABNB": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ABT": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ACN": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "AEE": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AIZ": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AKAM": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ALL": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ALLE": "WHEN_ISSUED_START_MATCH",
    "AMAT": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AMCR": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AMD": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "AMGN": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AMP": "WHEN_ISSUED_START_MATCH",
    "AMZN": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ANET": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "APO": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "APP": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "APTV": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "AVGO": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AWK": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "AXON": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "BG": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "BKR": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "BLK": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "BR": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "BRK.B": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "BX": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "CAT": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "CBOE": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "CBRE": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "CRM": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "CSCO": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "CVX": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "GE": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "GOOGL": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "GS": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "HD": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "JNJ": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "LLY": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "MA": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "MCD": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "META": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "MSFT": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "NEE": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "NFLX": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "NVDA": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "ORCL": "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED",
    "PG": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "RTX": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "SCHW": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "TMUS": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
    "TSLA": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "UNH": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "V": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
    "WMT": "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH",
}

_NEW_REVIEWED_SYMBOLS = frozenset(
    {
        "ABT",
        "ACN",
        "AEE",
        "ALL",
        "AMAT",
        "AMCR",
        "AMGN",
        "APO",
        "BG",
        "BKR",
        "BLK",
        "BR",
        "BRK.B",
        "BX",
        "CBOE",
        "CBRE",
    }
)

_DEFERRED_REASONS = {
    "ALGN": (
        "Tiingo begins 2001-01-30 after the sourced public-trading start 2001-01-26; "
        "canonical promotion remains blocked until the missing sessions are independently resolved."
    ),
    "ARES": (
        "Accepted primary-source filings conflict on whether ARES public trading began "
        "2014-05-01 or 2014-05-02; Tiingo begins 2014-05-02, so promotion remains blocked "
        "until the boundary discrepancy is independently reconciled."
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
    "BLDR": (
        "Tiingo begins 2005-06-28 after the sourced Nasdaq BLDR public-trading start "
        "2005-06-22; canonical promotion remains blocked until the missing initial sessions "
        "are independently resolved."
    ),
    "CARR": (
        "Tiingo begins a CARR-labelled series on 2020-03-19, but Carrier's SEC filing states "
        "that when-issued trading used CARR WI and regular-way CARR trading began 2020-04-03; "
        "provider alias ownership of the pre-regular-way observations must be resolved first."
    ),
    "COST": (
        "Tiingo COST begins in 1996 while Price/Costco traded under PCCW before the 1997 "
        "transition to COST; the exact trading-date boundary has not yet been established from "
        "an accepted primary source."
    ),
    "HON": (
        "The current Honeywell registrant is the AlliedSignal legal survivor of the 1999 merger, "
        "while the Tiingo HON series begins in 1996; ownership of the provider's pre-merger HON "
        "history by the permanent successor identity remains unresolved."
    ),
    "JPM": (
        "The current JPMorgan Chase registrant descends through the Chemical/Chase legal survivor; "
        "the Tiingo JPM series begins in 1996 and the pre-merger ticker/issuer ownership boundary "
        "has not yet been resolved explicitly."
    ),
    "MRK": (
        "The 2009 Merck/Schering-Plough transaction used a successor/survivor structure that makes "
        "the permanent-issuer ownership of the pre-transaction Tiingo MRK continuity series "
        "ambiguous without a dedicated lineage adjudication."
    ),
    "MS": (
        "The current Morgan Stanley registrant is the Dean Witter legal successor from the 1997 "
        "combination; the Tiingo MS history beginning in 1996 cannot be assigned to the permanent "
        "successor identity until its pre-combination ticker ownership is explicitly sourced."
    ),
    "XOM": (
        "Exxon is the legal survivor of the 1999 Mobil merger and later became Exxon Mobil, but "
        "the exact pre-merger Exxon ticker boundary needed to label the 1996 Tiingo continuity "
        "series has not yet been verified from an accepted primary source."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[1]
    root = args.root.expanduser().resolve()
    cases_path = repository_root / "configs" / "tiingo_symbol_lineage_cases_v0.11.json"
    seeds_path = repository_root / "configs" / "tiingo_reviewed_identity_seeds_v0.11.json"

    try:
        validate_workspace_location(root, repository_root=repository_root)
        workspace = load_operator_workspace(root)
        verification = verify_operator_workspace(workspace)
        if not verification.is_consistent:
            raise OperatorWorkspaceError(
                "durable evidence is inconsistent; reviewed identity expansion is blocked fail-closed"
            )

        profile_path = workspace.root / "evidence" / "tiingo-profile" / "profile.json"
        if not profile_path.is_file():
            raise OperatorWorkspaceError("Tiingo profile is missing; run profile-tiingo first")

        cases = load_lineage_case_source(cases_path)
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

        seed_set = load_reviewed_identity_seed_source(seeds_path)
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
