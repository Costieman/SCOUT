from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from trade_scout.data.providers.tiingo_lineage_audit import (
    audit_tiingo_profile_lineage,
    persist_tiingo_lineage_audit,
)
from trade_scout.data.providers.tiingo_lineage_case_source import load_lineage_case_source
from trade_scout.data.reviewed_identity_seed_source import load_reviewed_identity_seed_source
from trade_scout.data.reviewed_identity_snapshot import build_reviewed_identity_snapshot_candidate

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
    "CSCO": "1996-01-02",
    "CVX": "1996-01-02",
    "GE": "1996-01-02",
    "GOOGL": "2004-08-19",
    "GS": "1999-05-04",
    "HD": "1996-01-02",
    "JNJ": "1996-01-02",
    "LLY": "1996-01-02",
    "MA": "2006-05-25",
    "MCD": "1996-01-02",
    "META": "2012-05-18",
    "MSFT": "1996-01-02",
    "NEE": "1996-01-02",
    "NFLX": "2002-05-23",
    "NVDA": "1999-01-22",
    "ORCL": "1996-01-02",
    "PG": "1996-01-02",
    "RTX": "1996-01-02",
    "SCHW": "1996-01-02",
    "TMUS": "2007-04-19",
    "TSLA": "2010-06-29",
    "UNH": "1996-01-02",
    "V": "2008-03-19",
    "WMT": "1996-01-02",
}
_DEFERRED = {"ALGN", "BAC", "BKNG", "COST", "HON", "JPM", "MRK", "MS", "XOM"}


def test_v07_composes_prior_review_with_24_sourced_targets(tmp_path: Path) -> None:
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

    cases = load_lineage_case_source(
        _REPOSITORY_ROOT / "configs" / "tiingo_symbol_lineage_cases_v0.6.json"
    )
    audit = audit_tiingo_profile_lineage(profile_path=profile_path, cases=cases)
    audit_path = tmp_path / "audit.json"
    persist_tiingo_lineage_audit(audit_path, audit)

    classifications = {item.source_symbol: item.classification for item in audit.observations}
    assert audit.case_count == 42
    assert audit.profiled_case_count == 42
    assert Counter(classifications.values()) == {
        "CURRENT_SYMBOL_EFFECTIVE_DATE_MATCH": 25,
        "CURRENT_SYMBOL_OR_LATER_HISTORY_OBSERVED": 7,
        "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED": 8,
        "WHEN_ISSUED_START_MATCH": 2,
    }
    assert _DEFERRED.isdisjoint(classifications)

    seed_set = load_reviewed_identity_seed_source(
        _REPOSITORY_ROOT / "configs" / "tiingo_reviewed_identity_seeds_v0.7.json"
    )
    assert seed_set.snapshot_version == "tiingo-reviewed-identity-candidate-v0.7"
    review_ids = {item.review_id for item in seed_set.seeds}
    assert len(review_ids) == 42
    assert "rir-000010" not in review_ids
    assert {f"rir-{number:06d}" for number in range(20, 44)} <= review_ids

    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=seed_set,
        lineage_audit_path=audit_path,
    )
    assert len(candidate.instruments) == 42
    assert len(candidate.provider_series_links) == 42
    assert len(candidate.symbol_history) == 57
    assert candidate.coverage_gaps == ()
    assert candidate.promotion_ready is True
    assert {item.query_symbol for item in candidate.provider_series_links} == set(
        _EXPECTED_FIRST_DATES
    )

    expected_histories = {
        "CVX": [
            ("CHV", "XNYS", "1996-01-02", "2001-10-09"),
            ("CVX", "XNYS", "2001-10-10", None),
        ],
        "GOOGL": [
            ("GOOG", "XNAS", "2004-08-19", "2014-04-02"),
            ("GOOGL", "XNAS", "2014-04-03", None),
        ],
        "META": [
            ("FB", "XNAS", "2012-05-18", "2022-06-08"),
            ("META", "XNAS", "2022-06-09", None),
        ],
        "NEE": [
            ("FPL", "XNYS", "1996-01-02", "2010-06-22"),
            ("NEE", "XNYS", "2010-06-23", None),
        ],
        "ORCL": [
            ("ORCL", "XNAS", "1986-03-12", "2013-07-14"),
            ("ORCL", "XNYS", "2013-07-15", None),
        ],
        "RTX": [
            ("UTX", "XNYS", "1996-01-02", "2020-04-02"),
            ("RTX", "XNYS", "2020-04-03", None),
        ],
        "TMUS": [
            ("PCS", "XNYS", "2007-04-19", "2013-04-30"),
            ("TMUS", "XNYS", "2013-05-01", "2015-10-26"),
            ("TMUS", "XNAS", "2015-10-27", None),
        ],
        "WMT": [
            ("WMT", "XNYS", "1996-01-02", "2025-12-08"),
            ("WMT", "XNAS", "2025-12-09", None),
        ],
    }
    instruments = {item.primary_symbol: item for item in candidate.instruments}
    for symbol, expected in expected_histories.items():
        instrument = instruments[symbol]
        actual = [
            (
                item.symbol,
                item.exchange,
                item.effective_from.isoformat(),
                item.effective_to.isoformat() if item.effective_to else None,
            )
            for item in candidate.symbol_history
            if item.instrument_id == instrument.instrument_id
        ]
        assert actual == expected
