"""Governed batch planning for Trade Scout research experiments.

The planner materializes an explicit run plan before execution. It preserves the declared search
space, assigns stable child labels, and enforces the distinction between exploratory sweeps and
frozen confirmatory research.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from trade_scout.experiments.contracts import ExperimentDefinition, JSONValue, ResearchMode
from trade_scout.experiments.serialization import sha256_json
from trade_scout.experiments.sweeps import expand_grid


@dataclass(frozen=True, slots=True)
class PlannedExperiment:
    """One materialized child definition within an immutable batch plan."""

    ordinal: int
    label: str
    definition: ExperimentDefinition
    configuration_checksum: str


@dataclass(frozen=True, slots=True)
class ExperimentBatchPlan:
    """Complete pre-execution plan for one single run or declared parameter sweep."""

    plan_id: str
    parent_definition: ExperimentDefinition
    parameter_grid: dict[str, tuple[JSONValue, ...]]
    children: tuple[PlannedExperiment, ...]
    search_space_checksum: str

    @property
    def run_count(self) -> int:
        """Return the exact number of child experiments that will be executed."""

        return len(self.children)


class ExperimentPlanningError(ValueError):
    """Raised when a requested research plan violates experiment-governance rules."""


def plan_experiment_batch(
    definition: ExperimentDefinition,
    parameter_grid: dict[str, Iterable[JSONValue]] | None = None,
) -> ExperimentBatchPlan:
    """Materialize and validate an auditable experiment run plan.

    Exploratory mode may expand a declared Cartesian parameter grid. Confirmatory mode must use a
    frozen analytical definition and therefore rejects any dimension containing alternative values.
    Production-monitoring mode likewise rejects search grids because live monitoring may observe a
    validated definition but may not optimize it.
    """

    frozen_grid = _freeze_grid(parameter_grid or {})
    _validate_grid_governance(definition.mode, frozen_grid)

    if frozen_grid:
        materialized = expand_grid(definition, frozen_grid)
    else:
        materialized = (definition,)

    children = tuple(
        PlannedExperiment(
            ordinal=index,
            label=f"{definition.name}__{index:04d}",
            definition=replace(child, parent_experiment_id=definition.parent_experiment_id),
            configuration_checksum=sha256_json(child.resolved_configuration),
        )
        for index, child in enumerate(materialized, start=1)
    )
    search_payload = {
        "parent": definition,
        "parameter_grid": frozen_grid,
        "child_configuration_checksums": [item.configuration_checksum for item in children],
    }
    search_space_checksum = sha256_json(search_payload)
    return ExperimentBatchPlan(
        plan_id=f"plan_{search_space_checksum[:20]}",
        parent_definition=definition,
        parameter_grid=frozen_grid,
        children=children,
        search_space_checksum=search_space_checksum,
    )


def validate_plan_unchanged(plan: ExperimentBatchPlan) -> None:
    """Verify that stored plan identity still matches its complete declared search space."""

    rebuilt = plan_experiment_batch(plan.parent_definition, plan.parameter_grid)
    if rebuilt.search_space_checksum != plan.search_space_checksum:
        raise ExperimentPlanningError("experiment batch plan search space has changed")
    if rebuilt.plan_id != plan.plan_id:
        raise ExperimentPlanningError("experiment batch plan identity has changed")
    if tuple(item.configuration_checksum for item in rebuilt.children) != tuple(
        item.configuration_checksum for item in plan.children
    ):
        raise ExperimentPlanningError("experiment batch child configurations have changed")


def _freeze_grid(
    parameter_grid: dict[str, Iterable[JSONValue]],
) -> dict[str, tuple[JSONValue, ...]]:
    frozen: dict[str, tuple[JSONValue, ...]] = {}
    for path, candidates in parameter_grid.items():
        if not path.strip():
            raise ExperimentPlanningError("parameter paths must be non-empty")
        values = tuple(candidates)
        if not values:
            raise ExperimentPlanningError(
                f"parameter grid dimension {path!r} must contain at least one value"
            )
        frozen[path] = values
    return frozen


def _validate_grid_governance(
    mode: ResearchMode,
    parameter_grid: dict[str, tuple[JSONValue, ...]],
) -> None:
    if mode is ResearchMode.EXPLORATORY:
        return
    alternatives = tuple(path for path, values in parameter_grid.items() if len(values) > 1)
    if alternatives:
        names = ", ".join(alternatives)
        raise ExperimentPlanningError(
            f"{mode.value} research requires a frozen definition; search dimensions: {names}"
        )
