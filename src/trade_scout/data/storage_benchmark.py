"""Benchmark harness for the accepted Parquet/DuckDB canonical-storage path."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import perf_counter

import duckdb

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    CanonicalDatasetNotFoundError,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import DailyBar, DatasetVersion


@dataclass(frozen=True, slots=True)
class StorageBenchmarkResult:
    """Measured storage characteristics for one explicitly described canonical sample."""

    dataset_version: DatasetVersion
    record_count: int
    unique_instrument_count: int
    first_trade_date: date
    last_trade_date: date
    parquet_bytes: int
    metadata_bytes: int
    promote_seconds: float
    full_load_seconds: float
    filtered_query_seconds: float
    filtered_query_count: int

    @property
    def records_per_parquet_megabyte(self) -> float:
        """Return physical row density without claiming a pass/fail threshold."""

        if self.parquet_bytes == 0:
            return 0.0
        return self.record_count / (self.parquet_bytes / 1_000_000)


def benchmark_canonical_storage(
    bars: Iterable[DailyBar],
    *,
    promotion: DatasetPromotionRequest,
    root: Path,
    query_start: date,
    query_end: date,
) -> StorageBenchmarkResult:
    """Measure promotion, full-load, and filtered-query behavior on one supplied sample."""

    if query_end < query_start:
        raise ValueError("benchmark query_end must be on or after query_start")

    materialized = tuple(bars)
    if not materialized:
        raise ValueError("storage benchmark requires at least one daily bar")

    store = CanonicalDailyBarStore(root)
    if store.get_manifest(promotion.dataset_version) is not None:
        raise ValueError("benchmark root already contains the requested dataset version")

    promote_started = perf_counter()
    manifest = store.promote(materialized, promotion)
    promote_seconds = perf_counter() - promote_started

    load_started = perf_counter()
    loaded = store.load(promotion.dataset_version)
    full_load_seconds = perf_counter() - load_started
    if len(loaded) != manifest.record_count:
        raise RuntimeError("full-load benchmark did not reproduce the promoted record count")

    parquet_path = root / manifest.parquet_relative_path
    query_started = perf_counter()
    connection = duckdb.connect()
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM read_parquet(?) WHERE trade_date BETWEEN ? AND ?",
            [str(parquet_path), query_start, query_end],
        ).fetchone()
    finally:
        connection.close()
    filtered_query_seconds = perf_counter() - query_started

    if row is None or not isinstance(row[0], int):
        raise RuntimeError("filtered benchmark query did not return an integer count")

    instrument_ids = {bar.instrument_id for bar in materialized}
    return StorageBenchmarkResult(
        dataset_version=manifest.dataset_version,
        record_count=manifest.record_count,
        unique_instrument_count=len(instrument_ids),
        first_trade_date=manifest.first_trade_date,
        last_trade_date=manifest.last_trade_date,
        parquet_bytes=parquet_path.stat().st_size,
        metadata_bytes=store.metadata_path.stat().st_size,
        promote_seconds=promote_seconds,
        full_load_seconds=full_load_seconds,
        filtered_query_seconds=filtered_query_seconds,
        filtered_query_count=row[0],
    )


def benchmark_registered_dataset(
    *,
    source_root: Path,
    dataset_version: DatasetVersion,
    benchmark_root: Path,
    query_start: date,
    query_end: date,
) -> StorageBenchmarkResult:
    """Replay one registered canonical dataset through a fresh benchmark store.

    The source dataset is checksum-verified by ``CanonicalDailyBarStore.load`` before replay. Its
    immutable provenance fields are copied into a new ``DatasetPromotionRequest`` and the exact
    canonical bars are promoted into a separate fresh root. This permits a representative real
    dataset to be benchmarked without another provider download while still exercising the normal
    promotion, Parquet, DuckDB, quality, and provenance path.

    The benchmark root must be distinct from the source root. This function measures an existing
    dataset; it does not decide whether that dataset is representative enough to satisfy Phase 1.
    """

    source_resolved = source_root.resolve()
    benchmark_resolved = benchmark_root.resolve()
    if source_resolved == benchmark_resolved:
        raise ValueError("benchmark root must be distinct from the source canonical root")

    source_store = CanonicalDailyBarStore(source_root)
    manifest = source_store.get_manifest(dataset_version)
    if manifest is None:
        raise CanonicalDatasetNotFoundError(str(dataset_version))

    bars = source_store.load(dataset_version)
    promotion = DatasetPromotionRequest(
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        primary_provider_id=manifest.primary_provider_id,
        created_at=manifest.created_at,
        source_batch_ids=manifest.source_batch_ids,
        transformation_version=manifest.transformation_version,
        adjustment_policy_version=manifest.adjustment_policy_version,
        universe_construction_version=manifest.universe_construction_version,
        quality_check_version=manifest.quality_check_version,
    )
    return benchmark_canonical_storage(
        bars,
        promotion=promotion,
        root=benchmark_root,
        query_start=query_start,
        query_end=query_end,
    )
