from __future__ import annotations

import json
from pathlib import Path

from trade_scout.data.providers.tiingo_lineage_audit import (
    audit_tiingo_profile_lineage,
    load_lineage_cases,
    persist_tiingo_lineage_audit,
)
from trade_scout.data.reviewed_identity_snapshot import (
    build_reviewed_identity_snapshot_candidate,
    load_reviewed_identity_seed_set,
)

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_EXPECTED_FIRST_DATES = {
    "A": "1999-11-18",
    "ABNB": "2020-12-10",
    "AIZ": "2004-02-05",
    "AKAM": "1999-10-29",
    "ALGN": "2001-01-26",
    "ALLE": "2013-11-18",
    "AMP": "2005-10-03",
    "AMZN": "1997-05-15",
    "ANET": "2014-06-06",
    "APP": "2021-04-15",
    "APTV": "2011-11-17",
    "AWK": "2008-04-23",
    "AXON": "2001-06-07",
}


def test_v04_reviewed_identity_configs_cover_thirteen_profiled_series(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "schema_version": "tiingo-durable-profile-v0.1",
                "symbols": [
                    {"source_symbol": symbol, "first_date": first_date}
                    for symbol, first_date in sorted(_EXPECTED_FIRST_DATES.items())
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_lineage_cases(
        _REPOSITORY_ROOT / "configs" / "tiingo_symbol_lineage_cases_v0.3.json"
    )
    audit = audit_tiingo_profile_lineage(profile_path=profile_path, cases=cases)
    audit_path = tmp_path / "audit.json"
    persist_tiingo_lineage_audit(audit_path, audit)

    seed_set = load_reviewed_identity_seed_set(
        _REPOSITORY_ROOT / "configs" / "tiingo_reviewed_identity_seeds_v0.4.json"
    )
    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=seed_set,
        lineage_audit_path=audit_path,
    )

    assert audit.case_count == 13
    assert audit.profiled_case_count == 13
    assert candidate.snapshot_version == "tiingo-reviewed-identity-candidate-v0.4"
    assert len(candidate.instruments) == 13
    assert len(candidate.provider_series_links) == 13
    assert len(candidate.symbol_history) == 17
    assert candidate.coverage_gaps == ()
    assert candidate.promotion_ready is True
    assert {item.query_symbol for item in candidate.provider_series_links} == set(
        _EXPECTED_FIRST_DATES
    )

    known_first_trade_dates = {
        item.primary_symbol: item.first_trade_date.isoformat()
        for item in candidate.instruments
        if item.first_trade_date is not None
    }
    for symbol in ("A", "AIZ", "AKAM", "ALGN", "AMP", "AMZN"):
        assert known_first_trade_dates[symbol] == _EXPECTED_FIRST_DATES[symbol]
