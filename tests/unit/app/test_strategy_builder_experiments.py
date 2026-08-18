from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pytest

from trade_scout.app.entry_strategy_registry import EntryFamily
from trade_scout.app.strategy_builder_entry_sweep import EntrySweepParameter
from trade_scout.app.strategy_builder_experiments import (
    StrategyBuilderExperimentRecorder,
    attach_experiment_record_html,
)
from trade_scout.app.strategy_builder_service import (
    StrategyBuilderError,
    StrategyBuilderRequest,
    StrategyBuilderSource,
)
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.data.contracts import (
    DailyBar,
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.experiments.contracts import ExperimentStatus, ResearchMode
from trade_scout.experiments.registry import DuckDBExperimentRegistry
from trade_scout.experiments.store import FileManifestStore


def _daily(index: int, *, dataset_version: str = "strategy-builder-test-v1") -> DailyBar:
    close = 100.0 + index * 0.35
    return DailyBar(
        instrument_id=InstrumentId("strategy_builder_capture_test"),
        trade_date=date(2024, 1, 2) + timedelta(days=index),
        open_raw=close,
        high_raw=close + 1.0,
        low_raw=close - 1.0,
        close_raw=close,
        volume_raw=1_000_000.0 + index,
        split_factor=1.0,
        dividend_cash=0.0,
        open_split_adjusted=close,
        high_split_adjusted=close + 1.0,
        low_split_adjusted=close - 1.0,
        close_split_adjusted=close,
        provider_id="synthetic",
        dataset_version=DatasetVersion(dataset_version),
        quality_status=QualityStatus.PASS,
    )


def _research(item: DailyBar) -> ResearchBar:
    assert item.open_split_adjusted is not None
    assert item.high_split_adjusted is not None
    assert item.low_split_adjusted is not None
    assert item.close_split_adjusted is not None
    return ResearchBar(
        instrument_id=item.instrument_id,
        trade_date=item.trade_date,
        open=item.open_split_adjusted,
        high=item.high_split_adjusted,
        low=item.low_split_adjusted,
        close=item.close_split_adjusted,
        volume=item.volume_raw,
        eligibility=True,
        quality_status=item.quality_status,
        dataset_version=item.dataset_version,
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


@dataclass(frozen=True, slots=True)
class _WindowSource:
    rows: tuple[DailyBar, ...]

    def available_universes(self) -> tuple[UniverseOption, ...]:
        return (UniverseOption("reviewed_canonical", "Synthetic reviewed cohort", False),)

    def research_series(self, universe_id: str) -> dict[str, tuple[ResearchBar, ...]]:
        assert universe_id == "reviewed_canonical"
        return {"AAA": tuple(_research(item) for item in self.rows)}

    def canonical_daily_bars(self, universe_id: str) -> tuple[DailyBar, ...]:
        assert universe_id == "reviewed_canonical"
        return self.rows

    def strategy_builder_latest_trade_date(self, universe_id: str) -> date:
        assert universe_id == "reviewed_canonical"
        return self.rows[-1].trade_date

    def strategy_builder_dataset_record_count(self, universe_id: str) -> int:
        assert universe_id == "reviewed_canonical"
        return len(self.rows)

    def strategy_builder_daily_bars(
        self,
        universe_id: str,
        *,
        signal_start: date,
        signal_end: date,
        warmup_observations: int,
    ) -> tuple[DailyBar, ...]:
        assert universe_id == "reviewed_canonical"
        assert signal_start <= signal_end
        assert warmup_observations >= 1
        return self.rows


class _BrokenSource:
    def available_universes(self) -> tuple[UniverseOption, ...]:
        raise RuntimeError("synthetic source failure")

    def research_series(self, universe_id: str) -> dict[str, tuple[ResearchBar, ...]]:
        raise AssertionError("not reached")

    def canonical_daily_bars(self, universe_id: str) -> tuple[DailyBar, ...]:
        raise AssertionError("not reached")


def _recorder(root: Path, dataset_version: str) -> StrategyBuilderExperimentRecorder:
    return StrategyBuilderExperimentRecorder(
        experiment_root=root,
        dataset_version=dataset_version,
        code_version="test-code-sha",
    )


def test_normal_strategy_run_persists_manifest_artifact_and_registry(tmp_path: Path) -> None:
    source = cast(StrategyBuilderSource, _WindowSource(tuple(_daily(i) for i in range(330))))
    recorder = _recorder(tmp_path, "strategy-builder-test-v1")
    request = StrategyBuilderRequest(
        entry_family=EntryFamily.FEATURE_EXPRESSION,
        expression="return_20 > 0",
        rank_feature="return_20",
        per_session_limit=50,
        horizon=5,
        lookback_years=1,
        fixed_percentages=(0.05,),
        trailing_percentages=(),
        atr_multiples=(),
        trailing_atr_multiples=(),
        entry_slippage_bps=5,
        exit_slippage_bps=5,
        stop_slippage_bps=10,
    )

    recorded = recorder.run_strategy(source, request)

    assert recorded.manifest.status is ExperimentStatus.SUCCEEDED
    assert recorded.report.entry_event_count > 0
    persisted = FileManifestStore(tmp_path).read_manifest(recorded.manifest.experiment_id)
    assert persisted.definition.mode is ResearchMode.EXPLORATORY
    assert persisted.definition.resolved_configuration["outcome"] == {
        "maximum_holding_period_sessions": 5,
        "forced_exit_at_maximum_holding_period": True,
    }
    assert persisted.definition.resolved_configuration["exit_candidates"] == {
        "hold_to_horizon_control": True,
        "fixed_stop_percentages": [5.0],
        "trailing_stop_percentages": [],
        "atr_stop_multiples": [],
        "trailing_atr_multiples": [],
    }
    artifact = FileManifestStore(tmp_path).read_stage_output(
        recorded.manifest.experiment_id, "strategy_builder"
    )
    assert artifact["dataset_version"] == "strategy-builder-test-v1"
    assert cast(int, artifact["entry_event_count"]) > 0
    indexed = DuckDBExperimentRegistry(recorder.registry_path).get(recorded.manifest.experiment_id)
    assert indexed.status is ExperimentStatus.SUCCEEDED
    assert indexed.dataset_version == "strategy-builder-test-v1"


def test_entry_sweep_persists_declared_search_space_and_point_results(tmp_path: Path) -> None:
    dataset_version = "entry-sweep-capture-test-v1"
    source = cast(
        StrategyBuilderSource,
        _WindowSource(tuple(_daily(i, dataset_version=dataset_version) for i in range(180))),
    )
    recorder = _recorder(tmp_path, dataset_version)
    request = StrategyBuilderRequest(
        lookback_years=1,
        horizon=5,
        expression="pi__moving_average__ma_distance_pct__close__p20__sma > 0",
        rank_feature="return_20",
        per_session_limit=500,
        fixed_percentages=(),
        trailing_percentages=(),
        atr_multiples=(),
        trailing_atr_multiples=(),
    )

    recorded = recorder.run_entry_sweep(
        source,
        request,
        target_feature_name="pi__moving_average__ma_distance_pct__close__p20__sma",
        parameter=EntrySweepParameter.PERIOD,
        values=(10.0, 20.0, 30.0),
    )

    persisted = FileManifestStore(tmp_path).read_manifest(recorded.manifest.experiment_id)
    variable = cast(
        dict[str, object], persisted.definition.resolved_configuration["research_variable"]
    )
    assert variable["declared_values"] == [10.0, 20.0, 30.0]
    assert variable["entry_populations_are_separate"] is True
    artifact = FileManifestStore(tmp_path).read_stage_output(
        recorded.manifest.experiment_id, "strategy_builder_entry_sweep"
    )
    assert artifact["declared_values"] == [10.0, 20.0, 30.0]
    assert len(cast(list[object], artifact["points"])) == 3
    assert (
        DuckDBExperimentRegistry(recorder.registry_path).get(recorded.manifest.experiment_id).status
        is ExperimentStatus.SUCCEEDED
    )


def test_failed_strategy_run_is_retained_in_registry(tmp_path: Path) -> None:
    recorder = _recorder(tmp_path, "strategy-builder-test-v1")
    request = StrategyBuilderRequest(
        expression="return_20 > 0",
        fixed_percentages=(),
        trailing_percentages=(),
        atr_multiples=(),
        trailing_atr_multiples=(),
    )

    with pytest.raises(StrategyBuilderError, match="was saved with FAILED status"):
        recorder.run_strategy(cast(StrategyBuilderSource, _BrokenSource()), request)

    failed = DuckDBExperimentRegistry(recorder.registry_path).query(status=ExperimentStatus.FAILED)
    assert len(failed) == 1
    assert failed[0].dataset_version == "strategy-builder-test-v1"


def test_saved_experiment_card_exposes_identity_without_claiming_validation(tmp_path: Path) -> None:
    source = cast(StrategyBuilderSource, _WindowSource(tuple(_daily(i) for i in range(330))))
    recorded = _recorder(tmp_path, "strategy-builder-test-v1").run_strategy(
        source,
        StrategyBuilderRequest(
            expression="return_20 > 0",
            horizon=5,
            lookback_years=1,
            fixed_percentages=(),
            trailing_percentages=(),
            atr_multiples=(),
            trailing_atr_multiples=(),
        ),
    )

    html = attach_experiment_record_html("<html><body><div></div></body></html>", recorded.manifest)

    assert recorded.manifest.experiment_id in html
    assert "Automatically saved" in html
    assert "EXPLORATORY" in html
    assert "VALIDATED" not in html
