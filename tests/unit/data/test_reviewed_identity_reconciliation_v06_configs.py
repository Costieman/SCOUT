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
    "AAPL": "1996-01-02",
    "ABBV": "2013-01-02",
    "ABNB": "2020-12-10",
    "AIZ": "2004-02-05",
    "AKAM": "1999-10-29",
    "ALLE": "2013-11-18",
    "AMD": "1996-01-02",
    "AMP": "2005-09-15",
    "AMZN": "1997-05-15",
    "ANET": "2014-06-06",
    "APP": "2021-04-15",
    "APTV": "2011-11-17",
    "AVGO": "2009-08-06",
    "AWK": "2008-04-23",
    "AXON": "2001-06-07",
    "CAT": "1996-01-02",
    "CRM": "2004-06-23",
}


def test_v06_adds_six_sourced_large_caps_without_absorbing_deferred_cases(
    tmp_path: Path,
) -> None:
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
        _REPOSITORY_ROOT / "configs" / "tiingo_symbol_lineage_cases_v0.5.json"
    )
    audit = audit_tiingo_profile_lineage(profile_path=profile_path, cases=cases)
    audit_path = tmp_path / "audit.json"
    persist_tiingo_lineage_audit(audit_path, audit)

    classifications = {item.source_symbol: item.classification for item in audit.observations}
    assert audit.case_count == 18
    assert audit.profiled_case_count == 18
    assert classifications["AAPL"] == "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED"
    assert classifications["ABBV"] == "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH"
    assert classifications["AMD"] == "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED"
    assert classifications["AVGO"] == "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH"
    assert classifications["CAT"] == "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED"
    assert classifications["CRM"] == "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH"
    assert classifications["ALLE"] == "WHEN_ISSUED_START_MATCH"
    assert classifications["AMP"] == "WHEN_ISSUED_START_MATCH"
    assert {"ALGN", "BAC", "BKNG", "COST"}.isdisjoint(classifications)

    seed_set = load_reviewed_identity_seed_set(
        _REPOSITORY_ROOT / "configs" / "tiingo_reviewed_identity_seeds_v0.6.json"
    )
    assert "rir-000010" not in {item.review_id for item in seed_set.seeds}

    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=seed_set,
        lineage_audit_path=audit_path,
    )

    assert candidate.snapshot_version == "tiingo-reviewed-identity-candidate-v0.6"
    assert len(candidate.instruments) == 18
    assert len(candidate.provider_series_links) == 18
    assert len(candidate.symbol_history) == 24
    assert candidate.coverage_gaps == ()
    assert candidate.promotion_ready is True
    assert {item.query_symbol for item in candidate.provider_series_links} == set(
        _EXPECTED_FIRST_DATES
    )

    amd = next(item for item in candidate.instruments if item.primary_symbol == "AMD")
    assert amd.first_trade_date is None
    amd_history = [
        item for item in candidate.symbol_history if item.instrument_id == amd.instrument_id
    ]
    assert [
        (
            item.symbol,
            item.exchange,
            item.effective_from.isoformat(),
            item.effective_to.isoformat() if item.effective_to else None,
        )
        for item in amd_history
    ] == [
        ("AMD", "XNYS", "1979-10-15", "2015-01-01"),
        ("AMD", "XNAS", "2015-01-02", None),
    ]

    aapl = next(item for item in candidate.instruments if item.primary_symbol == "AAPL")
    assert aapl.first_trade_date is not None
    assert aapl.first_trade_date.isoformat() == "1980-12-12"

    cat = next(item for item in candidate.instruments if item.primary_symbol == "CAT")
    assert cat.first_trade_date is None
