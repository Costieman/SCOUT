"""Tests for the fixed-cohort private-workspace Experiment A execution boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trade_scout.data.canonical_storage import CanonicalDailyBarStore, DatasetPromotionRequest
from trade_scout.data.contracts import DailyBar, DatasetVersion, InstrumentId, QualityStatus
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.trend_baseline_operator import (
    FIXED_REVIEWED_COHORT_SCOPE_WARNING,
    ExperimentAOperatorError,
    execute_experiment_a_fixed_cohort,
    preflight_experiment_a_fixed_cohort,
)

DATASET_VERSION = DatasetVersion("operator-experiment-a-v1")
STOCK = InstrumentId("stock-1")
BENCHMARK = InstrumentId("benchmark-1")


def _bar(instrument_id: InstrumentId, trade_date: date, close: float) -> DailyBar:
    return DailyBar(
        instrument_id=instrument_id,
        trade_date=trade_date,
        open_raw=close - 0.1,
        high_raw=close + 0.4,
        low_raw=close - 0.4,
        close_raw=close,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close - 0.1,
        high_split_adjusted=close + 0.4,
        low_split_adjusted=close - 0.4,
        close_split_adjusted=close,
        provider_id="fixture",
        dataset_version=DATASET_VERSION,
        quality_status=QualityStatus.PASS,
    )


def _store(tmp_path: Path, *, include_benchmark: bool = True) -> CanonicalDailyBarStore:
    store = CanonicalDailyBarStore(tmp_path / "canonical")
    dates = tuple(date(2025, 1, 2) + timedelta(days=index) for index in range(235))
    bars = tuple(_bar(STOCK, day, 100.0 + index * 0.5) for index, day in enumerate(dates))
    if include_benchmark:
        bars += tuple(_bar(BENCHMARK, day, 100.0 + index * 0.1) for index, day in enumerate(dates))
    store.promote(
        bars,
        DatasetPromotionRequest(
            dataset_id="operator-experiment-a",
            dataset_version=DATASET_VERSION,
            primary_provider_id="fixture",
            created_at=datetime(2026, 8, 13, tzinfo=UTC),
            source_batch_ids=("fixture",),
            transformation_version="fixture-v1",
            adjustment_policy_version="fixture-v1",
            universe_construction_version="fixed-cohort-fixture-v1",
            quality_check_version="fixture-v1",
        ),
    )
    return store


def test_preflight_requires_benchmark_inside_same_canonical_dataset(tmp_path: Path) -> None:
    store = _store(tmp_path, include_benchmark=False)

    with pytest.raises(ExperimentAOperatorError, match="missing benchmark"):
        preflight_experiment_a_fixed_cohort(
            store,
            dataset_version=DATASET_VERSION,
            benchmark_instrument_id=BENCHMARK,
        )


def test_fixed_cohort_preflight_discloses_selection_bias_boundary(tmp_path: Path) -> None:
    preflight = preflight_experiment_a_fixed_cohort(
        _store(tmp_path),
        dataset_version=DATASET_VERSION,
        benchmark_instrument_id=BENCHMARK,
    )

    assert preflight.research_instrument_ids == (STOCK,)
    assert preflight.scope_warning == FIXED_REVIEWED_COHORT_SCOPE_WARNING
    assert "not historical index membership" in preflight.scope_warning


def test_operator_executes_complete_t0_t6_batch_and_comparison(tmp_path: Path) -> None:
    store = _store(tmp_path)
    manifest_store = FileManifestStore(tmp_path / "experiments")

    result = execute_experiment_a_fixed_cohort(
        store,
        manifest_store,
        dataset_version=DATASET_VERSION,
        benchmark_instrument_id=BENCHMARK,
        code_version="test-code",
        config_schema_version="test-schema",
        outcome_horizons=(2, 3),
        sampling_stride=5,
        sma_slope_lookback=5,
        trailing_return_intervals=20,
        relative_strength_intervals=20,
    )

    assert result.succeeded
    assert result.batch.planned_count == 7
    assert result.batch.succeeded_count == 7
    assert result.batch.failed_count == 0
    assert len(result.comparison) == 14
    assert {row.trend_context.value for row in result.comparison} == {
        "T0",
        "T1",
        "T2",
        "T3",
        "T4",
        "T5",
        "T6",
    }
    assert {row.horizon for row in result.comparison} == {2, 3}
