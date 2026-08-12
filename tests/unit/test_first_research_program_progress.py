"""Tests for explicit A-J research-program progression gates."""

from __future__ import annotations

from pathlib import Path

import pytest

from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentManifest,
    ExperimentStatus,
    ResearchMode,
)
from trade_scout.experiments.first_research_program import FirstProgramExperiment
from trade_scout.experiments.program_progress import (
    ProgramAssignment,
    ProgramProgressionError,
    ProgramStepState,
    evaluate_first_research_program_progress,
)
from trade_scout.experiments.registry import DuckDBExperimentRegistry


def _register(
    registry: DuckDBExperimentRegistry,
    experiment_id: str,
    *,
    mode: ResearchMode = ResearchMode.EXPLORATORY,
    status: ExperimentStatus = ExperimentStatus.SUCCEEDED,
) -> None:
    definition = ExperimentDefinition(
        name=f"run_{experiment_id}",
        hypothesis="Synthetic A-J progression test",
        mode=mode,
        dataset_version="dataset_v1",
        universe_version="universe_v1",
        code_version="abc123",
        config_schema_version="0.1.0",
        resolved_configuration={"synthetic": True},
        hypothesis_family_id="consolidation_breakout",
    )
    registry.register(
        ExperimentManifest(
            experiment_id=experiment_id,
            definition=definition,
            status=status,
            created_at="2026-08-13T00:00:00+00:00",
            completed_at="2026-08-13T00:01:00+00:00" if status is not ExperimentStatus.RUNNING else None,
            manifest_checksum=f"checksum_{experiment_id}",
        )
    )


def test_empty_program_is_ready_for_experiment_a(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    progress = evaluate_first_research_program_progress(registry, ())

    assert not progress.complete
    assert not progress.blocked
    assert progress.next_step is not None
    assert progress.next_step.experiment is FirstProgramExperiment.A_TREND_BASELINE
    assert progress.require_next(FirstProgramExperiment.A_TREND_BASELINE).experiment is (
        FirstProgramExperiment.A_TREND_BASELINE
    )


def test_successful_a_advances_exactly_to_b(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    _register(registry, "exp_a")
    progress = evaluate_first_research_program_progress(
        registry,
        (ProgramAssignment(FirstProgramExperiment.A_TREND_BASELINE, "exp_a"),),
    )

    assert progress.steps[0].state is ProgramStepState.SUCCEEDED
    assert progress.next_step is not None
    assert progress.next_step.experiment is FirstProgramExperiment.B_DURATION
    with pytest.raises(ProgramProgressionError, match="next eligible experiment is B"):
        progress.require_next(FirstProgramExperiment.C_TIGHTNESS)


def test_failed_a_blocks_progression(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    _register(registry, "exp_a", status=ExperimentStatus.FAILED)
    progress = evaluate_first_research_program_progress(
        registry,
        (ProgramAssignment(FirstProgramExperiment.A_TREND_BASELINE, "exp_a"),),
    )

    assert progress.blocked
    assert progress.steps[0].state is ProgramStepState.FAILED
    with pytest.raises(ProgramProgressionError, match="blocked at A"):
        progress.require_next(FirstProgramExperiment.A_TREND_BASELINE)


def test_running_a_blocks_progression_until_terminal_success(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    _register(registry, "exp_a", status=ExperimentStatus.RUNNING)
    progress = evaluate_first_research_program_progress(
        registry,
        (ProgramAssignment(FirstProgramExperiment.A_TREND_BASELINE, "exp_a"),),
    )

    assert progress.blocked
    assert progress.steps[0].state is ProgramStepState.INCOMPLETE


def test_assignment_cannot_skip_unfinished_prior_step(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    _register(registry, "exp_b")

    with pytest.raises(ProgramProgressionError, match="assigned before all prior A-J steps succeed"):
        evaluate_first_research_program_progress(
            registry,
            (ProgramAssignment(FirstProgramExperiment.B_DURATION, "exp_b"),),
        )


def test_same_run_cannot_satisfy_two_program_steps(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    with pytest.raises(ValueError, match="cannot satisfy multiple"):
        evaluate_first_research_program_progress(
            registry,
            (
                ProgramAssignment(FirstProgramExperiment.A_TREND_BASELINE, "exp_shared"),
                ProgramAssignment(FirstProgramExperiment.B_DURATION, "exp_shared"),
            ),
        )


def test_validation_experiment_i_requires_confirmatory_mode(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    assignments: list[ProgramAssignment] = []
    for step in tuple(FirstProgramExperiment)[:8]:
        experiment_id = f"exp_{step.value.lower()}"
        _register(registry, experiment_id)
        assignments.append(ProgramAssignment(step, experiment_id))

    _register(registry, "exp_i", mode=ResearchMode.EXPLORATORY)
    assignments.append(
        ProgramAssignment(FirstProgramExperiment.I_COMBINED_VALIDATION, "exp_i")
    )
    progress = evaluate_first_research_program_progress(registry, tuple(assignments))

    assert progress.blocked
    assert progress.steps[8].state is ProgramStepState.MODE_INVALID
    assert "requires CONFIRMATORY mode" in progress.steps[8].reason


def test_confirmatory_i_and_j_can_complete_program(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    assignments: list[ProgramAssignment] = []
    for step in tuple(FirstProgramExperiment):
        experiment_id = f"exp_{step.value.lower()}"
        mode = (
            ResearchMode.CONFIRMATORY
            if step
            in {
                FirstProgramExperiment.I_COMBINED_VALIDATION,
                FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT,
            }
            else ResearchMode.EXPLORATORY
        )
        _register(registry, experiment_id, mode=mode)
        assignments.append(ProgramAssignment(step, experiment_id))

    progress = evaluate_first_research_program_progress(registry, tuple(assignments))

    assert progress.complete
    assert not progress.blocked
    assert progress.next_step is None
    with pytest.raises(ProgramProgressionError, match="already complete"):
        progress.require_next(FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT)


def test_production_monitoring_mode_is_invalid_inside_a_j_program(tmp_path: Path) -> None:
    registry = DuckDBExperimentRegistry(tmp_path / "registry.duckdb")
    _register(registry, "exp_a", mode=ResearchMode.PRODUCTION_MONITORING)
    progress = evaluate_first_research_program_progress(
        registry,
        (ProgramAssignment(FirstProgramExperiment.A_TREND_BASELINE, "exp_a"),),
    )

    assert progress.steps[0].state is ProgramStepState.MODE_INVALID
    assert progress.blocked
