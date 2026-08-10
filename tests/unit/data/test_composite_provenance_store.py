from pathlib import Path

import pytest

from trade_scout.data.composite_adjudication import CompositeAdjudicationState
from trade_scout.data.composite_evidence import CompositeCoverageState
from trade_scout.data.composite_promotion import CompositeRowProvenance
from trade_scout.data.composite_provenance_store import (
    CompositeProvenanceConflictError,
    CompositeProvenanceIntegrityError,
    CompositeProvenanceStore,
)
from trade_scout.data.contracts import DatasetVersion


def _record(*, source: str = "alpha_vantage") -> CompositeRowProvenance:
    return CompositeRowProvenance(
        instrument_id="instrument:spy",
        trade_date="2026-01-02",
        included=True,
        canonical_provider_id="trade_scout_composite",
        selected_source_provider_id=source,
        selected_source_provider_instrument_id=(
            "alpha_vantage:symbol:SPY" if source == "alpha_vantage" else "stooq:spy"
        ),
        evidence_state=CompositeCoverageState.BOTH_AGREE,
        adjudication_state=CompositeAdjudicationState.CORROBORATED,
        review_note="A+B raw OHLCV agree within tolerance",
        corroborating_provider_ids=("alpha_vantage", "stooq"),
    )


def test_round_trip_and_idempotent_rewrite(tmp_path: Path) -> None:
    store = CompositeProvenanceStore(tmp_path)
    version = DatasetVersion("ab-v0.1")
    manifest = store.write(version, (_record(),))
    repeated = store.write(version, (_record(),))

    assert repeated.checksum_sha256 == manifest.checksum_sha256
    assert store.load(manifest) == (_record(),)


def test_same_version_with_different_provenance_is_rejected(tmp_path: Path) -> None:
    store = CompositeProvenanceStore(tmp_path)
    version = DatasetVersion("ab-v0.1")
    store.write(version, (_record(),))

    with pytest.raises(CompositeProvenanceConflictError):
        store.write(version, (_record(source="stooq"),))


def test_checksum_verification_detects_tampering(tmp_path: Path) -> None:
    store = CompositeProvenanceStore(tmp_path)
    manifest = store.write(DatasetVersion("ab-v0.1"), (_record(),))
    path = tmp_path / manifest.relative_path
    path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(CompositeProvenanceIntegrityError):
        store.load(manifest)
