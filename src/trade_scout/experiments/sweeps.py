"""Explicit parameter-sweep planning for experiment child runs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from itertools import product

from trade_scout.experiments.contracts import ExperimentDefinition, JSONValue


def expand_grid(
    definition: ExperimentDefinition,
    parameter_grid: Mapping[str, Iterable[JSONValue]],
) -> tuple[ExperimentDefinition, ...]:
    """Expand a declared Cartesian grid into child experiment definitions.

    Dotted parameter paths address nested mappings in the resolved configuration. The complete grid
    is materialized before execution so the search space remains auditable.
    """

    paths = tuple(parameter_grid)
    values = tuple(tuple(parameter_grid[path]) for path in paths)
    if any(not path.strip() for path in paths):
        raise ValueError("parameter paths must be non-empty")
    if any(not candidates for candidates in values):
        raise ValueError("parameter grid dimensions must contain at least one value")

    children: list[ExperimentDefinition] = []
    for combination in product(*values):
        resolved = _deep_copy(definition.resolved_configuration)
        for path, value in zip(paths, combination, strict=True):
            _set_path(resolved, path, value)
        children.append(replace(definition, resolved_configuration=resolved))
    return tuple(children)


def _deep_copy(value: dict[str, JSONValue]) -> dict[str, JSONValue]:
    copied: dict[str, JSONValue] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            copied[key] = _deep_copy(item)
        elif isinstance(item, list):
            copied[key] = list(item)
        else:
            copied[key] = item
    return copied


def _set_path(config: dict[str, JSONValue], dotted_path: str, value: JSONValue) -> None:
    parts = dotted_path.split(".")
    if any(not part for part in parts):
        raise ValueError(f"invalid parameter path: {dotted_path!r}")
    cursor: dict[str, JSONValue] = config
    for part in parts[:-1]:
        child = cursor.get(part)
        if not isinstance(child, dict):
            raise KeyError(f"parameter path does not resolve to a mapping: {dotted_path}")
        cursor = child
    leaf = parts[-1]
    if leaf not in cursor:
        raise KeyError(f"parameter path does not exist: {dotted_path}")
    cursor[leaf] = value
