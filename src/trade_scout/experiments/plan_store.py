"""Filesystem persistence for immutable experiment batch plans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from trade_scout.experiments.contracts import ExperimentDefinition, JSONValue, ResearchMode
from trade_scout.experiments.planner import ExperimentBatchPlan, plan_experiment_batch
from trade_scout.experiments.serialization import canonical_json


class FileBatchPlanStore:
    """Persist minimal batch-plan specifications and verify them by reconstruction on read."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write(self, plan: ExperimentBatchPlan) -> Path:
        """Atomically persist the definition and complete declared parameter grid."""

        self._root.mkdir(parents=True, exist_ok=True)
        path = self._path(plan.plan_id)
        payload = {
            "plan_id": plan.plan_id,
            "search_space_checksum": plan.search_space_checksum,
            "parent_definition": plan.parent_definition,
            "parameter_grid": plan.parameter_grid,
        }
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(canonical_json(payload) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    def read(self, plan_id: str) -> ExperimentBatchPlan:
        """Load a persisted plan and fail if reconstruction changes its declared identity."""

        raw = cast(dict[str, object], json.loads(self._path(plan_id).read_text(encoding="utf-8")))
        stored_plan_id = str(raw["plan_id"])
        if stored_plan_id != plan_id:
            raise ValueError(
                f"batch plan file identity mismatch: expected {plan_id}, got {stored_plan_id}"
            )

        definition_raw = cast(dict[str, object], raw["parent_definition"])
        definition = _definition_from_mapping(definition_raw)
        grid_raw = cast(dict[str, list[JSONValue]], raw.get("parameter_grid", {}))
        grid = {path: tuple(values) for path, values in grid_raw.items()}
        rebuilt = plan_experiment_batch(definition, grid)

        stored_checksum = str(raw["search_space_checksum"])
        if rebuilt.search_space_checksum != stored_checksum:
            raise ValueError(f"batch plan checksum mismatch for {plan_id}")
        if rebuilt.plan_id != stored_plan_id:
            raise ValueError(f"batch plan deterministic identity mismatch for {plan_id}")
        return rebuilt

    def _path(self, plan_id: str) -> Path:
        if not plan_id or any(character in plan_id for character in "/\\"):
            raise ValueError("plan_id must be a non-empty path-safe identifier")
        return self._root / f"{plan_id}.json"


def _definition_from_mapping(raw: dict[str, object]) -> ExperimentDefinition:
    resolved = cast(dict[str, JSONValue], raw["resolved_configuration"])
    return ExperimentDefinition(
        name=str(raw["name"]),
        hypothesis=str(raw["hypothesis"]),
        mode=ResearchMode(str(raw["mode"])),
        dataset_version=str(raw["dataset_version"]),
        universe_version=str(raw["universe_version"]),
        code_version=str(raw["code_version"]),
        config_schema_version=str(raw["config_schema_version"]),
        resolved_configuration=resolved,
        hypothesis_family_id=_optional_string(raw.get("hypothesis_family_id")),
        parent_experiment_id=_optional_string(raw.get("parent_experiment_id")),
        random_seed=cast(int | None, raw.get("random_seed")),
    )


def _optional_string(value: object) -> str | None:
    return None if value is None else str(value)
