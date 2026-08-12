"""Progression gates for the controlled consolidation-breakout A-J research program.

This module does not decide whether evidence is economically persuasive. It only prevents later
program steps from being treated as eligible when their declared prerequisites are missing, failed,
or executed under an incompatible research-governance mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from trade_scout.experiments.contracts import ExperimentStatus, ResearchMode
from trade_scout.experiments.first_research_program import (
    FIRST_RESEARCH_PROGRAM,
    FirstProgramExperiment,
    ProgramStep,
)
from trade_scout.experiments.registry import ExperimentIndexRecord


class ExperimentRegistryReader(Protocol):
    """Minimal experiment-registry read boundary needed for program gating."""

    def get(self, experiment_id: str) -> ExperimentIndexRecord: ...


class ProgramStepState(StrEnum):
    """Observed state of one A-J program step."""

    NOT_ASSIGNED = "NOT_ASSIGNED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INCOMPLETE = "INCOMPLETE"
    MODE_INVALID = "MODE_INVALID"


@dataclass(frozen=True, slots=True)
class ProgramAssignment:
    """Explicit link between an A-J research-program step and one experiment run."""

    step: FirstProgramExperiment
    experiment_id: str

    def __post_init__(self) -> None:
        if not self.experiment_id.strip():
            raise ValueError("program assignment experiment_id must be non-empty")


@dataclass(frozen=True, slots=True)
class ProgramStepProgress:
    """Auditable progression state for one program step."""

    step: ProgramStep
    state: ProgramStepState
    experiment_id: str | None
    research_mode: ResearchMode | None
    experiment_status: ExperimentStatus | None
    reason: str


@dataclass(frozen=True, slots=True)
class FirstResearchProgramProgress:
    """Complete A-J progression assessment derived from explicit assignments and registry state."""

    steps: tuple[ProgramStepProgress, ...]

    @property
    def complete(self) -> bool:
        """Return true only when every A-J step has a successful, governance-valid run."""

        return all(item.state is ProgramStepState.SUCCEEDED for item in self.steps)

    @property
    def next_step(self) -> ProgramStep | None:
        """Return the first incomplete step, or None when the program is complete."""

        for item in self.steps:
            if item.state is not ProgramStepState.SUCCEEDED:
                return item.step
        return None

    @property
    def blocked(self) -> bool:
        """Return true when failure, incompleteness, or invalid governance blocks progression."""

        next_progress = next(
            (item for item in self.steps if item.state is not ProgramStepState.SUCCEEDED),
            None,
        )
        if next_progress is None:
            return False
        return next_progress.state in {
            ProgramStepState.FAILED,
            ProgramStepState.INCOMPLETE,
            ProgramStepState.MODE_INVALID,
        }

    def require_next(self, requested_step: FirstProgramExperiment) -> ProgramStep:
        """Fail unless the requested step is exactly the next eligible A-J step."""

        expected = self.next_step
        if expected is None:
            raise ProgramProgressionError("first research program is already complete")
        if self.blocked:
            progress = next(item for item in self.steps if item.step is expected)
            raise ProgramProgressionError(
                f"program progression is blocked at {expected.experiment.value}: {progress.reason}"
            )
        if expected.experiment is not requested_step:
            expected_value = expected.experiment.value
            requested_value = requested_step.value
            raise ProgramProgressionError(
                f"next eligible experiment is {expected_value}, not {requested_value}"
            )
        return expected


class ProgramProgressionError(RuntimeError):
    """Raised when an A-J execution request would bypass a declared research-program gate."""


def evaluate_first_research_program_progress(
    registry: ExperimentRegistryReader,
    assignments: tuple[ProgramAssignment, ...],
) -> FirstResearchProgramProgress:
    """Evaluate A-J progress without inferring assignments from experiment names or outputs."""

    by_step = _validate_assignments(assignments)
    progress: list[ProgramStepProgress] = []
    prerequisites_satisfied = True

    for step in FIRST_RESEARCH_PROGRAM:
        assignment = by_step.get(step.experiment)
        if assignment is None:
            progress.append(
                ProgramStepProgress(
                    step=step,
                    state=ProgramStepState.NOT_ASSIGNED,
                    experiment_id=None,
                    research_mode=None,
                    experiment_status=None,
                    reason="no experiment run has been explicitly assigned to this step",
                )
            )
            prerequisites_satisfied = False
            continue

        if not prerequisites_satisfied:
            raise ProgramProgressionError(
                f"experiment {step.experiment.value} is assigned before all prior A-J steps succeed"
            )

        record = registry.get(assignment.experiment_id)
        mode_error = _mode_error(step.experiment, record.mode)
        if mode_error is not None:
            state = ProgramStepState.MODE_INVALID
            reason = mode_error
            prerequisites_satisfied = False
        elif record.status is ExperimentStatus.SUCCEEDED:
            state = ProgramStepState.SUCCEEDED
            reason = "assigned experiment completed successfully under the required governance mode"
        elif record.status is ExperimentStatus.FAILED:
            state = ProgramStepState.FAILED
            reason = "assigned experiment failed and cannot satisfy the program prerequisite"
            prerequisites_satisfied = False
        else:
            state = ProgramStepState.INCOMPLETE
            reason = f"assigned experiment is not terminal-successful: {record.status.value}"
            prerequisites_satisfied = False

        progress.append(
            ProgramStepProgress(
                step=step,
                state=state,
                experiment_id=record.experiment_id,
                research_mode=record.mode,
                experiment_status=record.status,
                reason=reason,
            )
        )

    return FirstResearchProgramProgress(steps=tuple(progress))


def _validate_assignments(
    assignments: tuple[ProgramAssignment, ...],
) -> dict[FirstProgramExperiment, ProgramAssignment]:
    by_step: dict[FirstProgramExperiment, ProgramAssignment] = {}
    experiment_ids: set[str] = set()
    for assignment in assignments:
        if assignment.step in by_step:
            raise ValueError(f"duplicate program assignment for experiment {assignment.step.value}")
        if assignment.experiment_id in experiment_ids:
            raise ValueError("one experiment run cannot satisfy multiple A-J program steps")
        by_step[assignment.step] = assignment
        experiment_ids.add(assignment.experiment_id)
    return by_step


def _mode_error(step: FirstProgramExperiment, mode: ResearchMode) -> str | None:
    if mode is ResearchMode.PRODUCTION_MONITORING:
        return "A-J research-program experiments cannot run in PRODUCTION_MONITORING mode"
    if (
        step
        in {
            FirstProgramExperiment.I_COMBINED_VALIDATION,
            FirstProgramExperiment.J_WALK_FORWARD_HOLDOUT,
        }
        and mode is not ResearchMode.CONFIRMATORY
    ):
        return f"experiment {step.value} requires CONFIRMATORY mode with a frozen definition"
    return None
