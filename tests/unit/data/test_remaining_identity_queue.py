import json
from datetime import date
from pathlib import Path
from types import MappingProxyType

from trade_scout.data.contracts import InstrumentRecord, SecurityType, SymbolHistoryRecord
from trade_scout.data.remaining_identity_queue import build_remaining_identity_queue
from trade_scout.data.reviewed_identity_snapshot import (
    ProviderSeriesLink,
    ReviewedIdentitySnapshotCandidate,
    derive_reviewed_instrument_id,
    persist_reviewed_identity_snapshot_candidate,
)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_remaining_queue_excludes_locked_symbols(tmp_path: Path) -> None:
    reviewed = tmp_path / "reviewed.json"
    remaining = tmp_path / "remaining.json"
    instrument_id = derive_reviewed_instrument_id("locked-review")
    candidate = ReviewedIdentitySnapshotCandidate(
        schema_version="reviewed-identity-candidate-v0.1",
        snapshot_version="test-snapshot",
        primary_provider_id="trade_scout_review",
        identity_definition_version="test-identity-v1",
        symbol_history_definition_version="test-history-v1",
        identity_seed_sha256="a" * 64,
        lineage_audit_sha256="b" * 64,
        instruments=(
            InstrumentRecord(
                instrument_id=instrument_id,
                primary_symbol="LOCK",
                name="LOCK CORP",
                exchange="XNYS",
                security_type=SecurityType.COMMON_STOCK,
                currency="USD",
                first_trade_date=date(2000, 1, 3),
                delisting_date=None,
                provider_ids=MappingProxyType(
                    {
                        "trade_scout_review": "locked-review",
                        "tiingo": "tiingo-series:locked-review",
                    }
                ),
            ),
        ),
        symbol_history=(
            SymbolHistoryRecord(
                instrument_id=instrument_id,
                symbol="LOCK",
                exchange="XNYS",
                effective_from=date(2000, 1, 3),
                effective_to=None,
            ),
        ),
        provider_series_links=(
            ProviderSeriesLink(
                instrument_id=instrument_id,
                review_id="locked-review",
                provider_id="tiingo",
                provider_series_id="tiingo-series:locked-review",
                query_symbol="LOCK",
            ),
        ),
        coverage_gaps=(),
        evidence_refs=("https://example.invalid/lock",),
    )
    persist_reviewed_identity_snapshot_candidate(reviewed, candidate)
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
