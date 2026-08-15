import json
from pathlib import Path

from trade_scout.data.remaining_identity_queue import build_remaining_identity_queue


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_remaining_queue_excludes_locked_symbols(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.json"
    remaining = tmp_path / "remaining.json"
    _write(
        reviewed,
        {
            "schema_version": "reviewed-identity-snapshot-v0.1",
            "snapshot_version": "test",
            "primary_provider_id": "trade_scout_review",
            "identity_definition_version": "v1",
            "symbol_history_definition_version": "v1",
            "identity_seed_sha256": "a" * 64,
            "lineage_audit_sha256": "b" * 64,
            "instruments": [],
            "symbol_history": [],
            "provider_series_links": [
                {
                    "instrument_id": "tsi_11111111111111111111111111111111",
                    "review_id": "locked",
                    "provider_id": "tiingo",
                    "provider_series_id": "tiingo-series:locked",
                    "query_symbol": "LOCK",
                }
            ],
            "coverage_gaps": [],
            "evidence_refs": [],
        },
    )
    _write(
        remaining,
        {
            "resolutions": [
                {"source_symbol": "LOCK", "resolution_kind": "OLD"},
                {"source_symbol": "OPEN", "resolution_kind": "BOUNDARY"},
            ]
        },
    )

    summary = build_remaining_identity_queue(
        reviewed_candidate_path=reviewed,
        extended_remaining_path=remaining,
    )

    assert summary.reviewed_symbol_count == 1
    assert summary.locked_overlap_count == 1
    assert summary.queued_symbols == ("OPEN",)
    assert summary.reason_counts == {"BOUNDARY": 1}
