"""End-to-end tests for the first real Experiment A research-stage adapter."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from trade_scout.data.canonical_storage import (
    CanonicalDailyBarStore,
    DatasetPromotionRequest,
)
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    QualityStatus,
)
from trade_scout.experiments.contracts import ExperimentDefinition, ExperimentExecutionError
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore
from trade_scout.experiments.trend_baseline import (
    EXPERIMENT_A_SMA_50_PERIOD,
    EXPERIMENT_A_SMA_200_PERIOD,
    CanonicalTrendBaselineSource,
    ExperimentATrendBaselineStage,
    MembershipEligibilityResolver,
    experiment_a_definition,
)
from trade_scout.features.trend_context import TrendContext
from trade_scout.universe.eligibility import UniverseMembershipRecord

DATASET_VERSION = DatasetVersion("experiment-a-fixture-v1")
STOCK = InstrumentId("stock-1")
BENCHMARK = InstrumentId("benchmark-1")


def _daily_bar(instrument_id: InstrumentId, trade_date: date, close: float) -> DailyBar:
    return DailyBar(
        instrument_id=instrument_id,
        trade_date=trade_date,
        open_raw=close - 0.2,
        high_raw=close + 0.5,
        low_raw=close - 0.5,
        close_raw=close,
        volume_raw=1_000_000.0,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close - 0.2,
        high_split_adjusted=close + 0.5,
        low_split_adjusted=close - 0.5,
        close_split_adjusted=close,
        provider_id="fixture",
        dataset_version=DATASET_VERSION,
        quality_status=QualityStatus.PASS,
    )


def _canonical_store(tmp_path: Path) -> tuple[CanonicalDailyBarStore, tuple[date, ...]]:
    store = CanonicalDailyBarStore(tmp_path / "data")
    dates = tuple(date(2025, 1, 2) + timedelta(days=index) for index in range(230))
    bars = tuple(
        _daily_bar(STOCK, day, 100.0 + index * 0.5) for index, day in enumerate(dates)
    ) + tuple(_daily_bar(BENCHMARK, day, 100.0 + index * 0.1) for index, day in enumerate(dates))
    store.promote(
        bars,
        DatasetPromotionRequest(
            dataset_id="experiment-a-fixture",
            dataset_version=DATASET_VERSION,
            primary_provider_id="fixture",
            created_at=datetime(2026, 1, 20, tzinfo=UTC),
            source_batch_ids=("fixture-batch",),
            transformation_version="fixture-v1",
            adjustment_policy_version="fixture-v1",
            universe_construction_version="universe-v1",
            quality_check_version="fixture-v1",
        ),
    )
    return store, dates


def _membership(dates: tuple[date, ...]) -> tuple[UniverseMembershipRecord, ...]:
    return tuple(
        UniverseMembershipRecord(
            instrument_id=STOCK,
            as_of=day,
            eligible=True,
            exclusion_reasons=(),
            universe_version="universe-v1",
            dataset_version=DATASET_VERSION,
            measurement_as_of=day,
        )
        for day in dates
    )


def _definition(context: TrendContext) -> ExperimentDefinition:
    return experiment_a_definition(
        trend_context=context,
        dataset_version=str(DATASET_VERSION),
        universe_version="universe-v1",
        code_version="test-code",
        config_schema_version="0.1.0",
        outcome_horizons=(2, 3),
        sampling_stride=2,
        sma_slope_lookback=5,
        trailing_return_intervals=20,
        relative_strength_intervals=20,
    )


def test_definition_preserves_specified_50_and_200_session_periods() -> None:
    definition = _definition(TrendContext.T4)
    config = definition.resolved_configuration["experiment_a"]

    assert isinstance(config, dict)
    assert config["sma_200_period"] == EXPERIMENT_A_SMA_200_PERIOD == 200
    assert config["sma_50_period"] == EXPERIMENT_A_SMA_50_PERIOD == 50


def test_experiment_a_runs_from_canonical_store_through_experiment_runner(tmp_path: Path) -> None:
    canonical, dates = _canonical_store(tmp_path)
    eligibility = MembershipEligibilityResolver(_membership(dates), universe_version="universe-v1")
    source = CanonicalTrendBaselineSource(
        canonical,
        eligibility,
        benchmark_instrument_id=BENCHMARK,
    )
    manifest_store = FileManifestStore(tmp_path / "experiments")
    runner = ExperimentRunner(manifest_store, id_factory=lambda: "experiment_A_T1")

    manifest = runner.run(_definition(TrendContext.T1), (ExperimentATrendBaselineStage(source),))
    output = manifest_store.read_stage_output(manifest.experiment_id, "trend_baseline")

    assert manifest.status.value == "SUCCEEDED"
    assert output["program_experiment"] == "A"
    assert output["trend_context"] == "T1"
    assert output["instrument_count"] == 1
    assert output["instruments_with_signals"] == 1
    measured = output["measured_outcome_count"]
    assert isinstance(measured, int) and measured > 0
    summaries = output["summaries"]
    assert isinstance(summaries, list)
    first = summaries[0]
    assert isinstance(first, dict)
    assert isinstance(first["sample_size"], int) and first["sample_size"] > 0
    assert first["positive_fraction"] == 1.0


def test_t6_uses_explicit_benchmark_relative_strength(tmp_path: Path) -> None:
    canonical, dates = _canonical_store(tmp_path)
    eligibility = MembershipEligibilityResolver(_membership(dates), universe_version="universe-v1")
    source = CanonicalTrendBaselineSource(
        canonical,
        eligibility,
        benchmark_instrument_id=BENCHMARK,
    )
    manifest_store = FileManifestStore(tmp_path / "experiments")
    runner = ExperimentRunner(manifest_store, id_factory=lambda: "experiment_A_T6")

    manifest = runner.run(_definition(TrendContext.T6), (ExperimentATrendBaselineStage(source),))
    output = manifest_store.read_stage_output(manifest.experiment_id, "trend_baseline")

    signal_count = output["qualifying_signal_count_before_stride"]
    measured = output["measured_outcome_count"]
    assert output["trend_context"] == "T6"
    assert isinstance(signal_count, int) and signal_count > 0
    assert isinstance(measured, int) and measured > 0


def test_t6_fails_closed_without_benchmark_series(tmp_path: Path) -> None:
    canonical, dates = _canonical_store(tmp_path)
    eligibility = MembershipEligibilityResolver(_membership(dates), universe_version="universe-v1")
    source = CanonicalTrendBaselineSource(canonical, eligibility)
    runner = ExperimentRunner(
        FileManifestStore(tmp_path / "experiments"),
        id_factory=lambda: "experiment_A_missing_benchmark",
    )

    with pytest.raises(ExperimentExecutionError, match="T6 requires benchmark bars"):
        runner.run(_definition(TrendContext.T6), (ExperimentATrendBaselineStage(source),))


def test_missing_membership_fails_closed_to_ineligible(tmp_path: Path) -> None:
    canonical, dates = _canonical_store(tmp_path)
    eligibility = MembershipEligibilityResolver((), universe_version="universe-v1")
    source = CanonicalTrendBaselineSource(
        canonical,
        eligibility,
        benchmark_instrument_id=BENCHMARK,
    )
    manifest_store = FileManifestStore(tmp_path / "experiments")
    runner = ExperimentRunner(manifest_store, id_factory=lambda: "experiment_A_no_membership")

    manifest = runner.run(_definition(TrendContext.T0), (ExperimentATrendBaselineStage(source),))
    output = manifest_store.read_stage_output(manifest.experiment_id, "trend_baseline")

    assert dates
    assert output["instruments_with_signals"] == 0
    assert output["measured_outcome_count"] == 0
