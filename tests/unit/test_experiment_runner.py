from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from trade_scout.experiments import (
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentRunner,
    ExperimentStatus,
    FileManifestStore,
    ResearchMode,
    StageResult,
    expand_grid,
)


class TickClock:
    def __init__(self) -> None:
        self._value = datetime(2026, 8, 13, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self._value
        self._value += timedelta(seconds=1)
        return value


@dataclass
class StaticStage:
    name: str
    payload: dict[str, object]
    warning: str | None = None

    def run(self, context: object) -> StageResult:
        warnings = () if self.warning is None else (self.warning,)
        return StageResult(stage_name=self.name, outputs=self.payload, warnings=warnings)  # type: ignore[arg-type]


@dataclass
class FailingStage:
    name: str = "statistics"

    def run(self, context: object) -> StageResult:
        raise RuntimeError("synthetic statistical failure")


def definition() -> ExperimentDefinition:
    return ExperimentDefinition(
        name="synthetic_duration_scan",
        hypothesis="Longer consolidations may alter forward outcomes.",
        mode=ResearchMode.EXPLORATORY,
        dataset_version="synthetic_v1",
        universe_version="synthetic_universe_v1",
        code_version="test-sha",
        config_schema_version="0.1.0",
        resolved_configuration={
            "patterns": {"duration": 20, "max_range_pct": 8.0},
            "outcomes": {"horizons": [20, 60]},
        },
        hypothesis_family_id="consolidation_duration",
        random_seed=42,
    )


def test_successful_run_persists_verified_manifest_and_artifacts(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    runner = ExperimentRunner(store, clock=TickClock(), id_factory=lambda: "exp_test_success")

    manifest = runner.run(
        definition(),
        [
            StaticStage("events", {"event_count": 12}),
            StaticStage("outcomes", {"mean_return": 0.031}, warning="small synthetic sample"),
        ],
    )

    assert manifest.status is ExperimentStatus.SUCCEEDED
    assert manifest.manifest_checksum is not None
    assert [stage.stage_name for stage in manifest.stages] == ["events", "outcomes"]
    assert manifest.warnings == ("small synthetic sample",)
    assert (tmp_path / "exp_test_success" / "artifacts" / "events.json").exists()
    assert store.read_manifest("exp_test_success") == manifest


def test_failed_run_records_failure_before_raising(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    runner = ExperimentRunner(store, clock=TickClock(), id_factory=lambda: "exp_test_failure")

    with pytest.raises(ExperimentExecutionError) as error:
        runner.run(definition(), [StaticStage("events", {"event_count": 3}), FailingStage()])

    assert error.value.experiment_id == "exp_test_failure"
    persisted = store.read_manifest("exp_test_failure")
    assert persisted.status is ExperimentStatus.FAILED
    assert persisted.failure_type == "RuntimeError"
    assert persisted.failure_message == "synthetic statistical failure"
    assert [stage.stage_name for stage in persisted.stages] == ["events"]


def test_reproduction_uses_exact_source_definition(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    ids = iter(("exp_original", "exp_reproduction"))
    runner = ExperimentRunner(store, clock=TickClock(), id_factory=lambda: next(ids))
    stages = [StaticStage("events", {"event_count": 5})]

    original = runner.run(definition(), stages)
    reproduced = runner.reproduce(original.experiment_id, stages)

    assert reproduced.definition == original.definition
    assert reproduced.reproduction_of == original.experiment_id
    assert reproduced.experiment_id != original.experiment_id
    assert reproduced.stages[0].output_checksum == original.stages[0].output_checksum


def test_duplicate_stage_names_fail_before_creating_run(tmp_path: Path) -> None:
    store = FileManifestStore(tmp_path)
    runner = ExperimentRunner(store, clock=TickClock(), id_factory=lambda: "should_not_exist")

    with pytest.raises(ValueError, match="unique"):
        runner.run(
            definition(),
            [StaticStage("events", {"a": 1}), StaticStage("events", {"b": 2})],
        )

    assert not (tmp_path / "should_not_exist").exists()


def test_parameter_grid_materializes_complete_declared_search_space() -> None:
    base = definition()

    children = expand_grid(
        base,
        {
            "patterns.duration": [10, 20, 30],
            "patterns.max_range_pct": [6.0, 8.0],
        },
    )

    assert len(children) == 6
    observed = {
        (
            child.resolved_configuration["patterns"]["duration"],  # type: ignore[index]
            child.resolved_configuration["patterns"]["max_range_pct"],  # type: ignore[index]
        )
        for child in children
    }
    assert observed == {(10, 6.0), (10, 8.0), (20, 6.0), (20, 8.0), (30, 6.0), (30, 8.0)}
    assert base.resolved_configuration["patterns"] == {"duration": 20, "max_range_pct": 8.0}
