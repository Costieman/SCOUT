"""Tests for governed experiment planning and batch execution."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from trade_scout.experiments.batch import BatchFailurePolicy, ExperimentBatchExecutor
from trade_scout.experiments.contracts import (
    ExperimentContext,
    ExperimentDefinition,
    ExperimentStatus,
    ResearchMode,
    StageResult,
)
from trade_scout.experiments.planner import (
    ExperimentPlanningError,
    plan_experiment_batch,
    validate_plan_unchanged,
)
from trade_scout.experiments.runner import ExperimentRunner
from trade_scout.experiments.store import FileManifestStore


def _definition(mode: ResearchMode = ResearchMode.EXPLORATORY) -> ExperimentDefinition:
    return ExperimentDefinition(
        name="duration_surface",
        hypothesis="Duration may alter post-breakout outcomes.",
        mode=mode,
        dataset_version="dataset_v1",
        universe_version="universe_v1",
        code_version="abc123",
        config_schema_version="0.1.0",
        resolved_configuration={
            "pattern": {"duration": 20, "max_range": 0.10},
            "outcome": {"horizon": 20},
        },
        hypothesis_family_id="consolidation_breakout",
    )


class _Stage:
    def __init__(self, name: str, *, fail_duration: int | None = None) -> None:
        self._name = name
        self._fail_duration = fail_duration

    @property
    def name(self) -> str:
        return self._name

    def run(self, context: ExperimentContext) -> StageResult:
        pattern = context.definition.resolved_configuration["pattern"]
        assert isinstance(pattern, dict)
        duration = pattern["duration"]
        assert isinstance(duration, int)
        if duration == self._fail_duration:
            raise RuntimeError(f"synthetic failure at duration={duration}")
        return StageResult(stage_name=self.name, outputs={"duration": duration})


def test_exploratory_plan_materializes_complete_cartesian_search_space() -> None:
    plan = plan_experiment_batch(
        _definition(),
        {
            "pattern.duration": (10, 20, 30),
            "outcome.horizon": (20, 60),
        },
    )

    assert plan.run_count == 6
    assert tuple(child.ordinal for child in plan.children) == (1, 2, 3, 4, 5, 6)
    assert len({child.configuration_checksum for child in plan.children}) == 6
    assert plan.plan_id.startswith("plan_")
    validate_plan_unchanged(plan)


def test_plan_identity_is_deterministic_for_same_definition_and_search_space() -> None:
    first = plan_experiment_batch(_definition(), {"pattern.duration": (10, 20, 30)})
    second = plan_experiment_batch(_definition(), {"pattern.duration": (10, 20, 30)})

    assert first.plan_id == second.plan_id
    assert first.search_space_checksum == second.search_space_checksum


def test_confirmatory_research_rejects_parameter_search() -> None:
    with pytest.raises(ExperimentPlanningError, match="requires a frozen definition"):
        plan_experiment_batch(
            _definition(ResearchMode.CONFIRMATORY),
            {"pattern.duration": (20, 30)},
        )


def test_confirmatory_research_allows_single_frozen_value() -> None:
    plan = plan_experiment_batch(
        _definition(ResearchMode.CONFIRMATORY),
        {"pattern.duration": (20,)},
    )
    assert plan.run_count == 1


def test_production_monitoring_rejects_live_parameter_search() -> None:
    with pytest.raises(ExperimentPlanningError, match="requires a frozen definition"):
        plan_experiment_batch(
            _definition(ResearchMode.PRODUCTION_MONITORING),
            {"pattern.duration": (20, 30)},
        )


def test_plan_validation_detects_modified_search_identity() -> None:
    plan = plan_experiment_batch(_definition(), {"pattern.duration": (10, 20)})
    tampered = replace(plan, search_space_checksum="not-the-real-checksum")
    with pytest.raises(ExperimentPlanningError, match="search space has changed"):
        validate_plan_unchanged(tampered)


def test_batch_continue_policy_retains_failed_child_and_completes_plan(tmp_path: Path) -> None:
    ids = iter(("exp_1", "exp_2", "exp_3"))
    runner = ExperimentRunner(
        FileManifestStore(tmp_path / "runs"),
        id_factory=lambda: next(ids),
    )
    executor = ExperimentBatchExecutor(runner)
    plan = plan_experiment_batch(_definition(), {"pattern.duration": (10, 20, 30)})

    summary = executor.execute(
        plan,
        lambda _definition: (_Stage("measure", fail_duration=20),),
        failure_policy=BatchFailurePolicy.CONTINUE,
    )

    assert summary.complete
    assert summary.attempted_count == 3
    assert summary.succeeded_count == 2
    assert summary.failed_count == 1
    assert tuple(record.status for record in summary.records) == (
        ExperimentStatus.SUCCEEDED,
        ExperimentStatus.FAILED,
        ExperimentStatus.SUCCEEDED,
    )


def test_batch_fail_fast_policy_stops_after_first_failed_child(tmp_path: Path) -> None:
    ids = iter(("exp_1", "exp_2", "exp_3"))
    runner = ExperimentRunner(
        FileManifestStore(tmp_path / "runs"),
        id_factory=lambda: next(ids),
    )
    executor = ExperimentBatchExecutor(runner)
    plan = plan_experiment_batch(_definition(), {"pattern.duration": (10, 20, 30)})

    summary = executor.execute(
        plan,
        lambda _definition: (_Stage("measure", fail_duration=20),),
        failure_policy=BatchFailurePolicy.FAIL_FAST,
    )

    assert not summary.complete
    assert summary.attempted_count == 2
    assert summary.succeeded_count == 1
    assert summary.failed_count == 1
