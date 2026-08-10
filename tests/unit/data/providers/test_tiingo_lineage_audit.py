import json
from pathlib import Path

from trade_scout.data.providers.tiingo_lineage_audit import (
    audit_tiingo_profile_lineage,
    load_lineage_cases,
)


def _write_profile(path: Path) -> None:
    payload = {
        "schema_version": "tiingo-durable-profile-v0.1",
        "symbols": [
            {"source_symbol": "APTV", "first_date": "2011-11-17"},
            {"source_symbol": "ALLE", "first_date": "2013-11-18"},
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_cases(path: Path) -> None:
    payload = {
        "schema_version": "tiingo-lineage-audit-cases-v0.1",
        "cases": [
            {
                "source_symbol": "APTV",
                "current_symbol_effective_date": "2017-12-05",
                "regular_way_start": "2017-12-05",
                "when_issued_start": null,
                "lineage_events": [
                    {
                        "effective_date": "2017-12-05",
                        "from_symbol": "DLPH",
                        "to_symbol": "APTV",
                        "event_type": "TICKER_CHANGE",
                        "source_title": "source",
                        "source_url": "https://example.invalid/aptv"
                    }
                ]
            },
            {
                "source_symbol": "ALLE",
                "current_symbol_effective_date": "2013-12-02",
                "regular_way_start": "2013-12-02",
                "when_issued_start": "2013-11-18",
                "lineage_events": [
                    {
                        "effective_date": "2013-11-18",
                        "from_symbol": null,
                        "to_symbol": "ALLE WI",
                        "event_type": "WHEN_ISSUED",
                        "source_title": "source",
                        "source_url": "https://example.invalid/alle"
                    }
                ]
            },
            {
                "source_symbol": "AXON",
                "current_symbol_effective_date": "2021-01-26",
                "regular_way_start": null,
                "when_issued_start": null,
                "lineage_events": [
                    {
                        "effective_date": "2021-01-26",
                        "from_symbol": "AAXN",
                        "to_symbol": "AXON",
                        "event_type": "TICKER_CHANGE",
                        "source_title": "source",
                        "source_url": "https://example.invalid/axon"
                    }
                ]
            }
        ]
    }
    text = json.dumps(payload).replace("null", "null")
    path.write_text(text, encoding="utf-8")


def test_audit_classifies_predecessor_and_when_issued_history(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.json"
    cases_path = tmp_path / "cases.json"
    _write_profile(profile_path)
    _write_cases(cases_path)

    audit = audit_tiingo_profile_lineage(
        profile_path=profile_path,
        cases=load_lineage_cases(cases_path),
    )
    by_symbol = {item.source_symbol: item for item in audit.observations}

    assert by_symbol["APTV"].classification == "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED"
    assert by_symbol["ALLE"].classification == "WHEN_ISSUED_START_MATCH"
    assert by_symbol["AXON"].classification == "NOT_PROFILED"
    assert audit.profiled_case_count == 2
