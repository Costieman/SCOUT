"""Deterministic follow-up plans for one-variable Strategy Builder research.

This module turns an already-computed one-dimensional response surface into a bounded next sweep.
It deliberately stops the iteration when the surface is flat and materially dominated by the hold
control rather than repeatedly optimizing the least-bad historical cell.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from statistics import median

from trade_scout.app.strategy_builder_entry_sweep import StrategyBuilderEntrySweepReport
from trade_scout.app.strategy_parameter_analysis import ParameterSurfaceAnalysis
from trade_scout.risk.exit_policies import ExitFamily, TargetFamily
from trade_scout.statistics.exit_research import ExitPolicySummary, ExitResearchComparison


@dataclass(frozen=True, slots=True)
class StrategicFollowupPlan:
    """Machine-actionable next sweep, or an explicit reason to stop refining this variable."""

    status: str
    message: str
    sweep_variable: str | None = None
    from_value: float | None = None
    to_value: float | None = None
    step_value: float | None = None
    button_label: str = "Run suggested next sweep"

    @property
    def can_run(self) -> bool:
        return (
            self.sweep_variable is not None
            and self.from_value is not None
            and self.to_value is not None
            and self.step_value is not None
        )


@dataclass(frozen=True, slots=True)
class _Sweep:
    variable: str
    values: tuple[float, ...]
    expectancies: tuple[float, ...]
    control_expectancy: float | None


def build_exit_followup(comparison: ExitResearchComparison) -> StrategicFollowupPlan | None:
    """Return the next bounded exit sweep, or stop when further expectancy honing is low value."""

    sweep = _largest_exit_sweep(comparison)
    if sweep is None or len(sweep.values) < 3:
        return None
    return _plan(
        sweep=sweep,
        shape=_shape(sweep.expectancies),
        integer_step=False,
        allow_zero=False,
    )


def build_entry_followup(
    report: StrategyBuilderEntrySweepReport,
    analysis: ParameterSurfaceAnalysis,
) -> StrategicFollowupPlan | None:
    """Return a bounded follow-up for the entry parameter represented by ``report``."""

    points = tuple(item for item in report.points if item.expectancy is not None)
    if len(points) < 3:
        return None
    ordered = tuple(sorted(points, key=lambda item: item.value))
    sweep = _Sweep(
        variable=f"entry::{report.target_feature_name}::{report.parameter.value}",
        values=tuple(item.value for item in ordered),
        expectancies=tuple(float(item.expectancy) for item in ordered if item.expectancy is not None),
        control_expectancy=None,
    )
    return _plan(
        sweep=sweep,
        shape=analysis.shape,
        integer_step=report.parameter.value != "standard_deviations",
        allow_zero=False,
    )


def _plan(
    *,
    sweep: _Sweep,
    shape: str,
    integer_step: bool,
    allow_zero: bool,
) -> StrategicFollowupPlan:
    values = sweep.values
    expectancies = sweep.expectancies
    best_index = max(range(len(expectancies)), key=expectancies.__getitem__)
    best_value = values[best_index]
    spread = max(expectancies) - min(expectancies)
    steps = tuple(right - left for left, right in pairwise(values) if right > left)
    step = float(median(steps)) if steps else max(abs(best_value) * 0.1, 1.0)

    if sweep.control_expectancy is not None:
        best_gap = max(expectancies) - sweep.control_expectancy
        if spread <= 0.0015 and best_gap <= -0.0025:
            return StrategicFollowupPlan(
                status="control_dominated_flat",
                message=(
                    "Stop honing this variable on expectancy: the tested surface is flat and every "
                    "managed value remains materially below the hold control. The next useful question "
                    "is whether the sacrificed return buys enough downside improvement (P05, profit "
                    "factor, holding time, stop/target behavior) to justify the exit. If not, switch the "
                    "Section 5 variable rather than repeatedly optimizing the least-bad cell."
                ),
            )

    if spread <= 0.00075:
        return StrategicFollowupPlan(
            status="flat_converged",
            message=(
                "This variable is effectively flat at the current resolution. Further narrowing is "
                "unlikely to add useful information; preserve the broad region and move to another "
                "research variable unless a secondary risk metric gives a specific reason to continue."
            ),
        )

    if shape == "increasing" and best_index == len(values) - 1:
        next_from = values[-1]
        next_step = max(step, 1.0) if integer_step else step
        next_to = next_from + next_step * 5
        return _action(
            sweep.variable,
            next_from,
            next_to,
            next_step,
            integer_step=integer_step,
            allow_zero=allow_zero,
            message="The best cell is still on the upper boundary, so extend the same variable before narrowing it.",
        )

    if shape == "decreasing" and best_index == 0:
        next_step = max(step, 1.0) if integer_step else step
        next_to = values[0]
        next_from = next_to - next_step * 5
        return _action(
            sweep.variable,
            next_from,
            next_to,
            next_step,
            integer_step=integer_step,
            allow_zero=allow_zero,
            message="The best cell is still on the lower boundary, so extend the same variable downward before narrowing it.",
        )

    next_step = max(step / 2.0, 1.0) if integer_step else max(step / 2.0, 0.01)
    next_from = max(values[0], best_value - step)
    next_to = min(values[-1], best_value + step)
    if next_to <= next_from:
        next_from = best_value - next_step * 2
        next_to = best_value + next_step * 2
    return _action(
        sweep.variable,
        next_from,
        next_to,
        next_step,
        integer_step=integer_step,
        allow_zero=allow_zero,
        message=(
            "The response has an interior best region. Run a finer local sweep around that region; "
            "repeat only while the new surface continues to resolve a stable direction."
        ),
    )


def _action(
    variable: str,
    start: float,
    end: float,
    step: float,
    *,
    integer_step: bool,
    allow_zero: bool,
    message: str,
) -> StrategicFollowupPlan:
    floor = 0.0 if allow_zero else (1.0 if integer_step else 0.01)
    start = max(floor, start)
    end = max(start, end)
    if integer_step:
        start = float(round(start))
        end = float(round(end))
        step = float(max(1, round(step)))
    return StrategicFollowupPlan(
        status="run_next",
        message=message,
        sweep_variable=variable,
        from_value=_round(start),
        to_value=_round(end),
        step_value=_round(step),
    )


def _largest_exit_sweep(comparison: ExitResearchComparison) -> _Sweep | None:
    hold = next(
        (
            item
            for item in comparison.policy_summaries
            if item.family is ExitFamily.HOLD_TO_HORIZON and item.target_family is None
        ),
        None,
    )
    managed = tuple(
        item
        for item in comparison.policy_summaries
        if item.family is not ExitFamily.HOLD_TO_HORIZON and item.expectancy is not None
    )
    candidates: list[_Sweep] = []

    for variable, family, parameter, multiplier in (
        ("fixed", ExitFamily.FIXED_PERCENT_STOP, "distance_pct", 100.0),
        ("trailing", ExitFamily.TRAILING_PERCENT_STOP, "distance_pct", 100.0),
        ("atr", ExitFamily.ATR_STOP, "atr_multiple", 1.0),
        ("trailing_atr", ExitFamily.TRAILING_ATR_STOP, "atr_multiple", 1.0),
    ):
        groups: dict[tuple[object, ...], list[ExitPolicySummary]] = {}
        for item in managed:
            if item.family is not family or parameter not in item.resolved_parameters:
                continue
            key = (item.target_family, tuple(sorted(item.target_parameters.items())))
            groups.setdefault(key, []).append(item)
        for rows in groups.values():
            candidate = _sweep_from_rows(
                rows,
                variable=variable,
                parameter=parameter,
                multiplier=multiplier,
                target=False,
                control=None if hold is None else hold.expectancy,
            )
            if candidate is not None:
                candidates.append(candidate)

    for variable, target_family, parameter, multiplier in (
        ("target_fixed", TargetFamily.FIXED_PERCENT, "gain_pct", 100.0),
        ("target_atr", TargetFamily.ATR_MULTIPLE, "atr_multiple", 1.0),
        ("target_r", TargetFamily.R_MULTIPLE, "r_multiple", 1.0),
    ):
        groups = {}
        for item in managed:
            if item.target_family is not target_family or parameter not in item.target_parameters:
                continue
            key = (item.family, tuple(sorted(item.resolved_parameters.items())))
            groups.setdefault(key, []).append(item)
        for rows in groups.values():
            candidate = _sweep_from_rows(
                rows,
                variable=variable,
                parameter=parameter,
                multiplier=multiplier,
                target=True,
                control=None if hold is None else hold.expectancy,
            )
            if candidate is not None:
                candidates.append(candidate)

    return max(candidates, key=lambda item: len(item.values)) if candidates else None


def _sweep_from_rows(
    rows: list[ExitPolicySummary],
    *,
    variable: str,
    parameter: str,
    multiplier: float,
    target: bool,
    control: float | None,
) -> _Sweep | None:
    pairs: list[tuple[float, float]] = []
    for item in rows:
        mapping = item.target_parameters if target else item.resolved_parameters
        raw = mapping.get(parameter)
        if raw is None or item.expectancy is None:
            continue
        pairs.append((float(raw) * multiplier, float(item.expectancy)))
    pairs.sort(key=lambda item: item[0])
    if len({value for value, _ in pairs}) < 3:
        return None
    return _Sweep(
        variable=variable,
        values=tuple(value for value, _ in pairs),
        expectancies=tuple(expectancy for _, expectancy in pairs),
        control_expectancy=control,
    )


def _shape(expectancies: tuple[float, ...]) -> str:
    if len(expectancies) < 3:
        return "mixed"
    diffs = tuple(right - left for left, right in pairwise(expectancies))
    spread = max(expectancies) - min(expectancies)
    tolerance = max(1e-12, spread * 0.08)
    threshold = max(1, (4 * len(diffs) + 4) // 5)
    if sum(diff >= -tolerance for diff in diffs) >= threshold and expectancies[-1] > expectancies[0] + tolerance:
        return "increasing"
    if sum(diff <= tolerance for diff in diffs) >= threshold and expectancies[-1] < expectancies[0] - tolerance:
        return "decreasing"
    return "mixed"


def _round(value: float) -> float:
    return round(value, 8)


__all__ = ["StrategicFollowupPlan", "build_entry_followup", "build_exit_followup"]
