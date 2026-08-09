from datetime import UTC, date, datetime

import pytest

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetNotFoundError,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.data.storage_benchmark import (
    benchmark_canonical_storage,
    benchmark_registered_dataset,
)

VERSION = DatasetVersion("benchmark_equities_v0.1.0")


def _bar(instrument_id: str, trade_date: date, close: float) -> DailyBar:
    return DailyBar(
        instrument_id=InstrumentId(instrument_id),
        trade_date=trade_date,
        open_raw=close - 0.5,
        high_raw=close + 1.0,
        low_raw=close - 1.0,
        close_raw=close,
        volume_raw=1_000_000,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close - 0.5,
        high_split_adjusted=close + 1.0,
        low_split_adjusted=close - 1.0,
        close_split_adjusted=close,
        provider_id="primary",
        dataset_version=VERSION,
        quality_status=QualityStatus.PASS,
    )


def _promotion() -> DatasetPromotionRequest:
    return DatasetPromotionRequest(
        dataset_id="benchmark_equities_daily",
        dataset_version=VERSION,
        primary_provider_id="primary",
        created_at=datetime(2026, 8, 8, 12, 0, tzinfo=UTC),
        source_batch_ids=("benchmark-batch",),
        transformation_version="benchmark-transform-v0.1.0",
        adjustment_policy_version="benchmark-adjustment-v0.1.0",
        universe_construction_version="benchmark-universe-v0.1.0",
        quality_check_version="benchmark-quality-v0.1.0",
    )


def _bars() -> tuple[DailyBar, ...]:
    return (
        _bar("tsi-1", date(2026, 8, 6), 100.0),
        _bar("tsi-1", date(2026, 8, 7), 101.0),
        _bar("tsi-2", date(2026, 8, 6), 50.0),
        _bar("tsi-2", date(2026, 8, 7), 51.0),
    )


def test_benchmark_harness_measures_storage_path_without_performance_claim(tmp_path) -> None:
    result = benchmark_canonical_storage(
        _bars(),
        promotion=_promotion(),
        root=tmp_path,
        query_start=date(2026, 8, 7),
        query_end=date(2026, 8, 7),
    )

    assert result.dataset_version == VERSION
    assert result.record_count == 4
    assert result.unique_instrument_count == 2
    assert result.first_trade_date == date(2026, 8, 6)
    assert result.last_trade_date == date(2026, 8, 7)
    assert result.filtered_query_count == 2
    assert result.parquet_bytes > 0
    assert result.metadata_bytes > 0
    assert result.promote_seconds >= 0.0
    assert result.full_load_seconds >= 0.0
    assert result.filtered_query_seconds >= 0.0
    assert result.records_per_parquet_megabyte > 0.0


def test_benchmark_rejects_reverse_query_window(tmp_path) -> None:
    with pytest.raises(ValueError, match="query_end"):
        benchmark_canonical_storage(
            (_bar("tsi-1", date(2026, 8, 6), 100.0),),
            promotion=_promotion(),
            root=tmp_path,
            query_start=date(2026, 8, 7),
            query_end=date(2026, 8, 6),
        )


def test_benchmark_root_must_be_fresh_for_requested_dataset_version(tmp_path) -> None:
    bars = (_bar("tsi-1", date(2026, 8, 6), 100.0),)
    benchmark_canonical_storage(
        bars,
        promotion=_promotion(),
        root=tmp_path,
        query_start=date(2026, 8, 6),
        query_end=date(2026, 8, 6),
    )

    with pytest.raises(ValueError, match="already contains"):
        benchmark_canonical_storage(
            bars,
            promotion=_promotion(),
            root=tmp_path,
            query_start=date(2026, 8, 6),
            query_end=date(2026, 8, 6),
        )


def test_registered_dataset_replay_preserves_source_and_provenance(tmp_path) -> None:
    source_root = tmp_path / "source"
    benchmark_root = tmp_path / "benchmark"
    source_store = CanonicalDailyBarStore(source_root)
    source_manifest = source_store.promote(_bars(), _promotion())
    source_checksum = source_manifest.parquet_checksum_sha256

    result = benchmark_registered_dataset(
        source_root=source_root,
        dataset_version=VERSION,
        benchmark_root=benchmark_root,
        query_start=date(2026, 8, 7),
        query_end=date(2026, 8, 7),
    )

    assert result.record_count == 4
    assert result.filtered_query_count == 2
    assert source_store.get_manifest(VERSION) == source_manifest
    assert source_store.get_manifest(VERSION).parquet_checksum_sha256 == source_checksum  # type: ignore[union-attr]

    replay_manifest = CanonicalDailyBarStore(benchmark_root).get_manifest(VERSION)
    assert replay_manifest is not None
    assert replay_manifest.dataset_id == source_manifest.dataset_id
    assert replay_manifest.primary_provider_id == source_manifest.primary_provider_id
    assert replay_manifest.source_batch_ids == source_manifest.source_batch_ids
    assert replay_manifest.transformation_version == source_manifest.transformation_version
    assert replay_manifest.adjustment_policy_version == source_manifest.adjustment_policy_version
    assert replay_manifest.universe_construction_version == source_manifest.universe_construction_version
    assert replay_manifest.quality_check_version == source_manifest.quality_check_version


def test_registered_dataset_replay_rejects_source_root_as_benchmark_root(tmp_path) -> None:
    CanonicalDailyBarStore(tmp_path).promote(_bars(), _promotion())

    with pytest.raises(ValueError, match="distinct"):
        benchmark_registered_dataset(
            source_root=tmp_path,
            dataset_version=VERSION,
            benchmark_root=tmp_path,
            query_start=date(2026, 8, 6),
            query_end=date(2026, 8, 7),
        )


def test_registered_dataset_replay_requires_registered_source_dataset(tmp_path) -> None:
    with pytest.raises(CanonicalDatasetNotFoundError):
        benchmark_registered_dataset(
            source_root=tmp_path / "source",
            dataset_version=VERSION,
            benchmark_root=tmp_path / "benchmark",
            query_start=date(2026, 8, 6),
            query_end=date(2026, 8, 7),
        )
