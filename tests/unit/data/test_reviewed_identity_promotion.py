import json
from pathlib import Path

import pytest

from trade_scout.data.instrument_storage import InstrumentMasterStore
from trade_scout.data.reviewed_identity_promotion import (
    ReviewedIdentityPromotionError,
    promote_reviewed_identity_candidate,
)
from trade_scout.data.reviewed_identity_snapshot import (
    build_reviewed_identity_snapshot_candidate,
    load_reviewed_identity_seed_set,
    persist_reviewed_identity_snapshot_candidate,
)

SEED_V01 = Path("configs/tiingo_reviewed_identity_seeds_v0.1.json")
SEED_V02 = Path("configs/tiingo_reviewed_identity_seeds_v0.2.json")


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


def _candidate_files(
    tmp_path: Path,
    seed_path: Path,
) -> tuple[Path, Path]:
    audit_path = tmp_path / "audit.json"
    candidate_path = tmp_path / "candidate.json"
    audit_path.write_text(json.dumps(_audit_payload()), encoding="utf-8")
    candidate = build_reviewed_identity_snapshot_candidate(
        seed_set=load_reviewed_identity_seed_set(seed_path),
        lineage_audit_path=audit_path,
    )
    persist_reviewed_identity_snapshot_candidate(candidate_path, candidate)
    return audit_path, candidate_path


def test_promotes_only_exact_rebuilt_gap_free_candidate(tmp_path: Path) -> None:
    audit_path, candidate_path = _candidate_files(tmp_path, SEED_V02)
    store_root = tmp_path / "canonical-store"

    result = promote_reviewed_identity_candidate(
        candidate_path=candidate_path,
        seed_path=SEED_V02,
        lineage_audit_path=audit_path,
        store_root=store_root,
    )

    assert result.already_registered is False
    assert result.candidate.promotion_ready is True
    assert result.manifest.instrument_count == 3
    assert result.manifest.symbol_history_count == 7
    assert result.manifest.source_batch_ids == (
        f"reviewed-identity-seed-sha256:{result.candidate.identity_seed_sha256}",
        f"tiingo-lineage-audit-sha256:{result.candidate.lineage_audit_sha256}",
    )

    loaded = InstrumentMasterStore(store_root).load(result.candidate.snapshot_version)
    assert loaded.instruments == result.candidate.instruments
    assert loaded.symbol_history == result.candidate.symbol_history


def test_promotion_is_idempotent_after_verified_registration(tmp_path: Path) -> None:
    audit_path, candidate_path = _candidate_files(tmp_path, SEED_V02)
    store_root = tmp_path / "canonical-store"

    first = promote_reviewed_identity_candidate(
        candidate_path=candidate_path,
        seed_path=SEED_V02,
        lineage_audit_path=audit_path,
        store_root=store_root,
    )
    second = promote_reviewed_identity_candidate(
        candidate_path=candidate_path,
        seed_path=SEED_V02,
        lineage_audit_path=audit_path,
        store_root=store_root,
    )

    assert first.already_registered is False
    assert second.already_registered is True
    assert first.manifest == second.manifest


def test_promotion_rejects_candidate_with_reviewed_coverage_gaps(tmp_path: Path) -> None:
    audit_path, candidate_path = _candidate_files(tmp_path, SEED_V01)

    with pytest.raises(ReviewedIdentityPromotionError, match="coverage gaps"):
        promote_reviewed_identity_candidate(
            candidate_path=candidate_path,
            seed_path=SEED_V01,
            lineage_audit_path=audit_path,
            store_root=tmp_path / "canonical-store",
        )


def test_promotion_rejects_candidate_not_equal_to_current_evidence_rebuild(tmp_path: Path) -> None:
    audit_path, candidate_path = _candidate_files(tmp_path, SEED_V02)
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    payload["evidence_refs"] = []
    candidate_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ReviewedIdentityPromotionError, match="does not exactly match"):
        promote_reviewed_identity_candidate(
            candidate_path=candidate_path,
            seed_path=SEED_V02,
            lineage_audit_path=audit_path,
            store_root=tmp_path / "canonical-store",
        )
