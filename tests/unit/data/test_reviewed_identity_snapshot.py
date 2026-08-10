import json
from pathlib import Path

import pytest

from trade_scout.data.reviewed_identity_snapshot import (
    ReviewedIdentitySnapshotError,
    build_reviewed_identity_snapshot_candidate,
    derive_reviewed_instrument_id,
    load_reviewed_identity_seed_set,
    load_reviewed_identity_snapshot_candidate,
    persist_reviewed_identity_snapshot_candidate,
    provider_series_link_for_query,
)

SEED_PATH = Path("configs/tiingo_reviewed_identity_seeds_v0.1.json")


def _audit_payload() -> dict[str, object]:
    return {
        "schema_version": "tiingo-lineage-audit-v0.1",
        "profile_path": "private/evidence/tiingo-profile/profile.json",
        "case_count": 3,
        "profiled_case_count": 3,
        "observations": [
            {
                "source_symbol": "APTV",
                "observed_first_date": "2011-11-17",
                "current_symbol_effective_date": "2017-12-05",
                "regular_way_start": "2017-12-05",
                "when_issued_start": "2017-11-21",
                "classification": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
                "lineage_events": [
                    {
                        "effective_date": "2017-12-05",
                        "from_symbol": "DLPH",
                        "to_symbol": "APTV",
                        "event_type": "TICKER_CHANGE_AFTER_SPINOFF",
                        "source_title": "source",
                        "source_url": "https://example.invalid/aptv",
                    }
                ],
            },
            {
                "source_symbol": "AXON",
                "observed_first_date": "2001-06-07",
                "current_symbol_effective_date": "2021-01-26",
                "regular_way_start": None,
                "when_issued_start": None,
                "classification": "PRE_CURRENT_SYMBOL_HISTORY_OBSERVED",
                "lineage_events": [
                    {
                        "effective_date": "2017-04-06",
                        "from_symbol": "TASR",
                        "to_symbol": "AAXN",
                        "event_type": "CORPORATE_NAME_AND_TICKER_CHANGE",
                        "source_title": "source",
                        "source_url": "https://example.invalid/axon-aaxn",
                    },
                    {
                        "effective_date": "2021-01-26",
                        "from_symbol": "AAXN",
                        "to_symbol": "AXON",
                        "event_type": "TICKER_CHANGE",
                        "source_title": "source",
                        "source_url": "https://example.invalid/axon",
                    },
                ],
            },
            {
                "source_symbol": "ALLE",
                "observed_first_date": "2013-11-18",
                "current_symbol_effective_date": "2013-12-02",
                "regular_way_start": "2013-12-02",
                "when_issued_start": "2013-11-18",
                "classification": "WHEN_ISSUED_START_MATCH",
                "lineage_events": [
                    {
                        "effective_date": "2013-11-18",
                        "from_symbol": None,
                        "to_symbol": "ALLE WI",
                        "event_type": "WHEN_ISSUED_TRADING_EXPECTED",
                        "source_title": "source",
                        "source_url": "https://example.invalid/alle",
                    }
                ],
            },
        ],
    }


def _write_audit(path: Path, payload: dict[str, object] | None = None) -> None:
    path.write_text(json.dumps(payload or _audit_payload()), encoding="utf-8")


def test_actual_reviewed_seed_config_uses_non_ticker_stable_series_ids() -> None:
    seed_set = load_reviewed_identity_seed_set(SEED_PATH)

    assert len(seed_set.seeds) == 3
    for seed in seed_set.seeds:
        assert seed.provider_links["tiingo"] != seed.provider_query_symbols["tiingo"]
        assert seed.provider_links["trade_scout_review"] == seed.review_id


def test_candidate_preserves_known_identity_gaps_instead_of_guessing(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    _write_audit(audit_path)
    seed_set = load_reviewed_identity_seed_set(SEED_PATH)

    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=seed_set,
        lineage_audit_path=audit_path,
    )

    assert len(candidate.instruments) == 3
    assert len(candidate.symbol_history) == 5
    assert len(candidate.provider_series_links) == 3
    assert candidate.promotion_ready is False
    assert candidate.fully_covered_instrument_count == 1

    gaps = {gap.query_symbol: gap for gap in candidate.coverage_gaps}
    assert set(gaps) == {"APTV", "AXON"}
    assert gaps["APTV"].known_predecessor_symbol == "DLPH"
    assert gaps["AXON"].known_predecessor_symbol == "TASR"
    assert gaps["APTV"].reason == "PREHISTORY_SYMBOL_START_UNRESOLVED"
    assert gaps["AXON"].reason == "PREHISTORY_SYMBOL_START_UNRESOLVED"


def test_reviewed_instrument_id_depends_on_review_identity_not_query_symbol() -> None:
    first = derive_reviewed_instrument_id("rir-000002")
    second = derive_reviewed_instrument_id("rir-000002")
    different = derive_reviewed_instrument_id("rir-000003")

    assert first == second
    assert first != different
    assert "AXON" not in str(first)


def test_provider_query_resolves_to_reviewed_stable_series(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    _write_audit(audit_path)
    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=load_reviewed_identity_seed_set(SEED_PATH),
        lineage_audit_path=audit_path,
    )

    link = provider_series_link_for_query(
        candidate,
        provider_id="tiingo",
        query_symbol="AXON",
    )

    assert link is not None
    assert link.provider_series_id == "tiingo-series:rir-000002"
    assert link.instrument_id == derive_reviewed_instrument_id("rir-000002")


def test_candidate_persistence_round_trip(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.json"
    output_path = tmp_path / "candidate.json"
    _write_audit(audit_path)
    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=load_reviewed_identity_seed_set(SEED_PATH),
        lineage_audit_path=audit_path,
    )

    persist_reviewed_identity_snapshot_candidate(output_path, candidate)
    loaded = load_reviewed_identity_snapshot_candidate(output_path)

    assert loaded == candidate
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert persisted["promotion_ready"] is False
    assert persisted["fully_covered_instrument_count"] == 1
    assert "open_raw" not in persisted
    assert "close_raw" not in persisted


def test_missing_audit_observation_fails_closed(tmp_path: Path) -> None:
    audit = _audit_payload()
    observations = audit["observations"]
    assert isinstance(observations, list)
    audit["observations"] = [
        item
        for item in observations
        if isinstance(item, dict) and item.get("source_symbol") != "AXON"
    ]
    audit_path = tmp_path / "audit.json"
    _write_audit(audit_path, audit)

    with pytest.raises(ReviewedIdentitySnapshotError, match="no matching Tiingo lineage"):
        build_reviewed_identity_snapshot_candidate(
            seed_set=load_reviewed_identity_seed_set(SEED_PATH),
            lineage_audit_path=audit_path,
        )


def test_overlapping_reviewed_symbol_history_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    axon = next(item for item in payload["seeds"] if item["primary_symbol"] == "AXON")
    axon["symbol_history"][1]["effective_from"] = "2021-01-25"
    config_path = tmp_path / "bad-seeds.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReviewedIdentitySnapshotError, match="overlapping symbol-history"):
        load_reviewed_identity_seed_set(config_path)
