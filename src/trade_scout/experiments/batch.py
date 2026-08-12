"""Execution orchestration for pre-materialized experiment batch plans.

Batch execution never chooses parameter combinations or analytical winners. It executes the complete declared
plan and records terminal state for every attempted child, including failed/null experiments.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from trade_scout.experiments.contracts import (
    ExperimentDefinition,
    ExperimentExecutionError,
    ExperimentStatus,
    ResearchStage,
)
from trade_scout.experiments.planner import ExperimentBatchPlan, validate_plan_unchanged
from trade_scout.experiments.runner import ExperimentRunner


class BatchFailurePolicy(StrEnum):
    """Explicit behavior when one child experiment fails."""

    CONTINUE = "CONTINUE"
    FAIL_FAST = "FAIL_FAST"


class StageFactory(Protocol):
    """Build fresh research-stage adapters for one child definition."""

    def __call__(self, definition: ExperimentDefinition) -> tuple[ResearchStage, ...]: ...


@dataclass(frozen=True, slots=True)
class BatchRunRecord:
    """Terminal execution state for one attempted planned child."""

    ordinal: int
    label: str
    experiment_id: str
    status: ExperimentStatus
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class BatchExecutionSummary:
    """Machine-readable outcome of executing a complete or fail-fast batch plan."""

    plan_id: str
    failure_policy: BatchFailurePolicy
    planned_count: int
    records: tuple[BatchRunRecord, ...]

    @property
    def attempted_count(self) -> int:
        return len(self.records)

    @property
    def succeeded_count(self) -> int:
        return sum(record.status is ExperimentStatus.SUCCEEDED for record in self.records)

    @property
    def failed_count(self) -> int:
        return sum(record.status is ExperimentStatus.FAILED for record in self.records)

    @property
    def complete(self) -> bool:
        return self.attempted_count == self.planned_count


class ExperimentBatchExecutor:
    """Execute every child in an immutable batch plan through the normal ExperimentRunner."""

    def __init__(self, runner: ExperimentRunner) -> None:
        self._runner = runner

    def execute(
        self,
        plan: ExperimentBatchPlan,
        stage_factory: StageFactory,
        *,
        failure_policy: BatchFailurePolicy = BatchFailurePolicy.CONTINUE,
    ) -> BatchExecutionSummary:
        """Execute a prevalidated plan without changing its analytical definitions."""

        validate_plan_unchanged(plan)
        records: list[BatchRunRecord] = []

        for child in plan.children:
            stages = stage_factory(child.definition)
            try:
                manifest = self._runner.run(child.definition, stages)
            except ExperimentExecutionError as error:
                records.append(
                    BatchRunRecord(
                        ordinal=child.ordinal,
                        label=child.label,
                        experiment_id=error.experiment_id,
                        status=ExperimentStatus.FAILED,
                        failure_message=str(error),
                    )
                )
                if failure_policy is BatchFailurePolicy.FAIL_FAST:
                    break
            else:
                records.append(
                    BatchRunRecord(
                        ordinal=child.ordinal,
                        label=child.label,
                        experiment_id=manifest.experiment_id,
                        status=manifest.status,
                    )
                )

        return BatchExecutionSummary(
            plan_id=plan.plan_id,
            failure_policy=failure_policy,
            planned_count=plan.run_count,
            records=tuple(records),
        )
