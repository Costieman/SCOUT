"""Complete parameter-surface contracts that prevent winner-only reporting."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import isfinite

from trade_scout.validation.contracts import SampleAccounting
from trade_scout.validation.evidence import ConfidenceInterval

ParameterValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class ParameterAxis:
    """One predeclared parameter dimension and all values tested along it."""

    name: str
    values: tuple[ParameterValue, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("parameter axis name must be non-empty")
        if not self.values:
            raise ValueError("parameter axis must contain at least one value")
        if len(set(self.values)) != len(self.values):
            raise ValueError("parameter axis values must be unique")
        for value in self.values:
            if isinstance(value, float) and not isfinite(value):
                raise ValueError("floating parameter values must be finite")


@dataclass(frozen=True, slots=True)
class ParameterCell:
    """One tested parameter combination and its descriptive result."""

    coordinates: tuple[tuple[str, ParameterValue], ...]
    metric: str
    estimate: float
    units: str
    sample: SampleAccounting
    interval: ConfidenceInterval | None = None
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.coordinates:
            raise ValueError("parameter cell coordinates must be non-empty")
        names = [name for name, _ in self.coordinates]
        if any(not name.strip() for name in names):
            raise ValueError("parameter coordinate names must be non-empty")
        if len(names) != len(set(names)):
            raise ValueError("parameter coordinate names must be unique")
        if not self.metric.strip():
            raise ValueError("parameter cell metric must be non-empty")
        if not isfinite(self.estimate):
            raise ValueError("parameter cell estimate must be finite")
        if not self.units.strip():
            raise ValueError("parameter cell units must be non-empty")
        if any(not warning.strip() for warning in self.warnings):
            raise ValueError("parameter cell warnings must be non-empty")

    @property
    def coordinate_map(self) -> dict[str, ParameterValue]:
        """Return a display-friendly copy of the immutable coordinates."""

        return dict(self.coordinates)


@dataclass(frozen=True, slots=True)
class ParameterSurface:
    """Complete declared parameter grid with one result for every tested cell."""

    surface_id: str
    axes: tuple[ParameterAxis, ...]
    metric: str
    units: str
    cells: tuple[ParameterCell, ...]

    def __post_init__(self) -> None:
        if not self.surface_id.strip():
            raise ValueError("surface_id must be non-empty")
        if not self.axes:
            raise ValueError("parameter surface must contain at least one axis")
        axis_names = [axis.name for axis in self.axes]
        if len(axis_names) != len(set(axis_names)):
            raise ValueError("parameter surface axis names must be unique")
        if not self.metric.strip() or not self.units.strip():
            raise ValueError("parameter surface metric and units must be non-empty")

        expected = set(self.declared_coordinates())
        observed: set[tuple[tuple[str, ParameterValue], ...]] = set()
        for cell in self.cells:
            if cell.metric != self.metric or cell.units != self.units:
                raise ValueError("all parameter cells must use the surface metric and units")
            coordinates = tuple(cell.coordinates)
            if coordinates in observed:
                raise ValueError("parameter surface contains duplicate cells")
            observed.add(coordinates)
        if observed != expected:
            missing = len(expected - observed)
            unexpected = len(observed - expected)
            raise ValueError(
                "parameter surface must retain the complete declared search space; "
                f"missing={missing}, unexpected={unexpected}"
            )

    def declared_coordinates(self) -> tuple[tuple[tuple[str, ParameterValue], ...], ...]:
        """Materialize the complete Cartesian grid in deterministic axis order."""

        coordinate_sets = product(*(axis.values for axis in self.axes))
        return tuple(
            tuple((axis.name, value) for axis, value in zip(self.axes, values, strict=True))
            for values in coordinate_sets
        )

    def cell_at(self, **coordinates: ParameterValue) -> ParameterCell:
        """Return one exact cell without ranking or choosing a best-performing value."""

        expected_names = tuple(axis.name for axis in self.axes)
        if set(coordinates) != set(expected_names):
            raise KeyError("cell lookup must specify every surface axis exactly once")
        key = tuple((name, coordinates[name]) for name in expected_names)
        for cell in self.cells:
            if cell.coordinates == key:
                return cell
        raise KeyError(f"parameter surface has no cell at {coordinates!r}")


def build_parameter_surface(
    *,
    surface_id: str,
    axes: tuple[ParameterAxis, ...],
    metric: str,
    units: str,
    cells: tuple[ParameterCell, ...],
) -> ParameterSurface:
    """Construct and completeness-check one persisted parameter surface."""

    return ParameterSurface(
        surface_id=surface_id,
        axes=axes,
        metric=metric,
        units=units,
        cells=cells,
    )
