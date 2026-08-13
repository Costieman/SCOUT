"""Tests for immutable canonical dataset composition."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from trade_scout.data.canonical_composition import (
    CANONICAL_COMPOSITION_TRANSFORMATION_VERSION,
    CanonicalCompositionError,
    compose_canonical_datasets,
)
from trade_scout.data.canonical_storage import CanonicalDailyBarStore, DatasetPromotionRequest
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus

RESEARCH = DatasetVersion("research-v1")
BENCHMARK = DatasetVersion("benchmark-v1")
COMPOSED = DatasetVersion("composed-v1")


def _bar(instrument: str, day: date, dataset: DatasetVersion) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument),
        trade_date=day,
        open_raw=100.0,
        high_raw=101.0,
        low_raw=99.0,
        close_raw=100.5,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=100.0,
        high_split_adjusted=101.0,
        low_split_adjusted=99.0,
        close_split_adjusted=100.5,
        provider_id="tiingo",
        dataset_version=dataset,
        quality_status=QualityStatus.PASS,
    )


def _promote(
    store: CanonicalDailyBarStore,
    version: DatasetVersion,
    instrument: str,
    *,
    day: date = date(2026, 8, 7),
) -> None:
    store.promote(
        (_bar(instrument, day, version),),
        DatasetPromotionRequest(
            dataset_id=f"dataset-{version}",
            dataset_version=version,
            primary_provider_id="tiingo",
            created_at=datetime(2026, 8, 13, tzinfo=UTC),
            source_batch_ids=(f"batch-{version}",),
            transformation_version="source-transform-v1",
            adjustment_policy_version="split-only-v1",
            universe_construction_version="source-universe-v1",
            quality_check_version="source-quality-v1",
        ),
    )


def test_composition_creates_new_immutable_version_and_preserves_sources(tmp_path: Path) -> None:
    store = CanonicalDailyBarStore(tmp_path)
    _promote(store, RESEARCH, "stock-1")
    _promote(store, BENCHMARK, "benchmark-1")

    result = compose_canonical_datasets(
        store,
        source_dataset_versions=(RESEARCH, BENCHMARK),
        target_dataset_id="experiment-a-input",
        target_dataset_version=COMPOSED,
        created_at=datetime(2026, 8, 13, tzinfo=UTC),
        universe_construction_version="research-plus-benchmark-v1",
    )

    assert result.source_dataset_versions == (RESEARCH, BENCHMARK)
    assert result.manifest.record_count == 2
    assert result.manifest.transformation_version == CANONICAL_COMPOSITION_TRANSFORMATION_VERSION
    assert result.manifest.source_batch_ids == ("batch-research-v1", "batch-benchmark-v1")
    assert {bar.dataset_version for bar in store.load(COMPOSED)} == {COMPOSED}
    assert {str(bar.instrument_id) for bar in store.load(COMPOSED)} == {
        "benchmark-1",
        "stock-1",
    }
    assert {bar.dataset_version for bar in store.load(RESEARCH)} == {RESEARCH}
    assert {bar.dataset_version for bar in store.load(BENCHMARK)} == {BENCHMARK}


def test_composition_rejects_overlapping_instrument_date_keys(tmp_path: Path) -> None:
    store = CanonicalDailyBarStore(tmp_path)
    _promote(store, RESEARCH, "same-instrument")
    _promote(store, BENCHMARK, "same-instrument")

    with pytest.raises(CanonicalCompositionError, match="overlapping instrument/date"):
        compose_canonical_datasets(
            store,
            source_dataset_versions=(RESEARCH, BENCHMARK),
            target_dataset_id="blocked",
            target_dataset_version=COMPOSED,
            created_at=datetime(2026, 8, 13, tzinfo=UTC),
            universe_construction_version="research-plus-benchmark-v1",
        )


def test_composition_requires_distinct_target_version(tmp_path: Path) -> None:
    store = CanonicalDailyBarStore(tmp_path)
    _promote(store, RESEARCH, "stock-1")
    _promote(store, BENCHMARK, "benchmark-1")

    with pytest.raises(CanonicalCompositionError, match="target dataset version"):
        compose_canonical_datasets(
            store,
            source_dataset_versions=(RESEARCH, BENCHMARK),
            target_dataset_id="blocked",
            target_dataset_version=RESEARCH,
            created_at=datetime(2026, 8, 13, tzinfo=UTC),
            universe_construction_version="research-plus-benchmark-v1",
        )
