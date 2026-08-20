# ruff: noqa: E501
"""Evidence-grounded next-experiment suggestions for Strategy Builder exit comparisons."""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.app.strategy_parameter_analysis import (
    ParameterEvidencePoint,
    ParameterSurfaceAnalysis,
    analyze_parameter_surface,
)
from trade_scout.risk.exit_policies import ExitFamily, TargetFamily
from trade_scout.statistics.exit_research import ExitPolicySummary, ExitResearchComparison


@dataclass(frozen=True, slots=True)
class StrategicExperimentOption:
    """One directional next experiment derived from the current descriptive result."""

    title: str
    direction: str
    proposed_range: str
    rationale: str
    falsifier: str


@dataclass(frozen=True, slots=True)
class StrategicNextStepAnalysis:
    """Plain-English interpretation and bounded research options for one completed run."""

    headline: str
    observation: str
    caution: str
    options: tuple[StrategicExperimentOption, ...]
    robustness: str = ""
    version: str = "strategy-next-step-v0.2"


@dataclass(frozen=True, slots=True)
class _ExitSweep:
    label: str
    unit: str
    points: tuple[ParameterEvidencePoint, ...]
    fixed_stop_special: bool = False


def analyze_strategic_next_steps(
    comparison: ExitResearchComparison,
) -> StrategicNextStepAnalysis:
    """Infer a directional experiment for any clean one-variable exit sweep."""

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
    if not managed:
        return StrategicNextStepAnalysis(
            headline="No managed-exit comparison is available yet.",
            observation="The run does not contain enough managed exit evidence to infer a parameter direction.",
            caution=_caution(comparison),
            options=(),
        )

    sweep = _largest_exit_sweep(managed)
    if sweep is not None and len(sweep.points) >= 3:
        surface = analyze_parameter_surface(
            parameter_label=sweep.label,
            unit_label=sweep.unit,
            points=sweep.points,
            control_expectancy=None if hold is None else hold.expectancy,
            special_ultra_tight_stop_branch=sweep.fixed_stop_special,
        )
        return _from_surface(surface, fixed_stop_special=sweep.fixed_stop_special)

    best = max(
        managed,
        key=lambda item: item.expectancy if item.expectancy is not None else float("-inf"),
    )
    hold_text = (
        "The hold control remains the higher-expectancy reference."
        if hold is not None
        and hold.expectancy is not None
        and best.expectancy is not None
        and best.expectancy < hold.expectancy
        else "The managed comparison should be replicated before narrowing parameters."
    )
    return StrategicNextStepAnalysis(
        headline="The current grid does not expose a clean one-dimensional direction.",
        observation=(
            f"The strongest managed row is {best.family.value.replace('_', ' ')} at "
            f"{_pct(best.expectancy)}, but the available rows do not isolate one parameter while "
            f"holding its partner components fixed. {hold_text}"
        ),
        caution=_caution(comparison),
        options=(
            StrategicExperimentOption(
                title="Run a cleaner local sweep",
                direction="Hold the entry population and every partner exit parameter fixed.",
                proposed_range="Choose one Section 5 exit dimension and test at least five ordered values around the current best row.",
                rationale="A single-variable response surface is more interpretable than a mixed policy grid.",
                falsifier="If neighboring values do not reproduce the apparent advantage, treat the current best row as unstable.",
            ),
        ),
    )


def _largest_exit_sweep(managed: tuple[ExitPolicySummary, ...]) -> _ExitSweep | None:
    candidates: list[_ExitSweep] = []

    stop_groups: dict[tuple[object, ...], list[ExitPolicySummary]] = {}
    for item in managed:
        stop = _stop_dimension(item)
        if stop is None:
            continue
        key = (
            item.family,
            stop[0],
            item.target_family,
            tuple(sorted(item.target_parameters.items())),
        )
        stop_groups.setdefault(key, []).append(item)
    for rows in stop_groups.values():
        dimension = _stop_dimension(rows[0])
        assert dimension is not None
        parameter_name, label, unit, multiplier = dimension
        values = [item.resolved_parameters.get(parameter_name) for item in rows]
        if None in values or len(set(values)) < 3:
            continue
        points = tuple(
            _evidence_point(
                item, value=float(item.resolved_parameters[parameter_name]) * multiplier
            )
            for item in rows
        )
        candidates.append(
            _ExitSweep(
                label=label,
                unit=unit,
                points=points,
                fixed_stop_special=(
                    rows[0].family is ExitFamily.FIXED_PERCENT_STOP
                    and rows[0].target_family is None
                ),
            )
        )

    target_groups: dict[tuple[object, ...], list[ExitPolicySummary]] = {}
    for item in managed:
        target = _target_dimension(item)
        if target is None:
            continue
        key = (
            item.family,
            tuple(sorted(item.resolved_parameters.items())),
            item.target_family,
            target[0],
        )
        target_groups.setdefault(key, []).append(item)
    for rows in target_groups.values():
        dimension = _target_dimension(rows[0])
        assert dimension is not None
        parameter_name, label, unit, multiplier = dimension
        values = [item.target_parameters.get(parameter_name) for item in rows]
        if None in values or len(set(values)) < 3:
            continue
        points = tuple(
            _evidence_point(item, value=float(item.target_parameters[parameter_name]) * multiplier)
            for item in rows
        )
        candidates.append(_ExitSweep(label=label, unit=unit, points=points))

    if not candidates:
        return None
    return max(candidates, key=lambda item: len(item.points))


def _stop_dimension(item: ExitPolicySummary) -> tuple[str, str, str, float] | None:
    if item.family is ExitFamily.FIXED_PERCENT_STOP:
        return "distance_pct", "Fixed stop distance", "%", 100.0
    if item.family is ExitFamily.TRAILING_PERCENT_STOP:
        return "distance_pct", "Trailing stop distance", "%", 100.0
    if item.family is ExitFamily.ATR_STOP:
        return "atr_multiple", "ATR stop multiple", "x ATR", 1.0
    if item.family is ExitFamily.TRAILING_ATR_STOP:
        return "atr_multiple", "Trailing ATR stop multiple", "x ATR", 1.0
    return None


def _target_dimension(item: ExitPolicySummary) -> tuple[str, str, str, float] | None:
    if item.target_family is TargetFamily.FIXED_PERCENT:
        return "gain_pct", "Fixed profit target", "%", 100.0
    if item.target_family is TargetFamily.ATR_MULTIPLE:
        return "atr_multiple", "ATR profit target", "x ATR", 1.0
    if item.target_family is TargetFamily.R_MULTIPLE:
        return "r_multiple", "Risk-multiple profit target", "R", 1.0
    return None


def _evidence_point(item: ExitPolicySummary, *, value: float) -> ParameterEvidencePoint:
    return ParameterEvidencePoint(
        value=value,
        sample_size=item.sample_size,
        expectancy=item.expectancy,
        win_probability=item.win_probability,
        profit_factor=item.profit_factor,
        tail_loss_p05=item.tail_loss_p05,
        average_holding_period_sessions=item.average_holding_period_sessions,
        stop_out_rate=item.stop_out_rate,
        target_hit_rate=item.target_hit_rate,
    )


def _from_surface(
    surface: ParameterSurfaceAnalysis,
    *,
    fixed_stop_special: bool,
) -> StrategicNextStepAnalysis:
    headline = surface.headline
    if fixed_stop_special and surface.shape == "increasing":
        headline = (
            "Wider stops are the strongest next direction; also test a separate ultra-tight regime."
        )
    elif fixed_stop_special and surface.shape == "decreasing":
        headline = "Tighter stops are the strongest next direction."
    options = tuple(
        StrategicExperimentOption(
            title=item.title,
            direction=item.direction,
            proposed_range=item.proposed_range,
            rationale=item.rationale,
            falsifier=item.falsifier,
        )
        for item in surface.options
    )
    return StrategicNextStepAnalysis(
        headline=headline,
        observation=surface.observation,
        robustness=surface.robustness,
        caution=surface.caution,
        options=options,
    )


def _caution(comparison: ExitResearchComparison) -> str:
    return (
        f"Exploratory only: {comparison.complete_event_count} complete events on one frozen historical population. "
        "A directional next experiment is a hypothesis, not a validated trading recommendation; out-of-sample testing, multiplicity control, execution sensitivity and portfolio constraints still matter."
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.2f}%"


__all__ = [
    "StrategicExperimentOption",
    "StrategicNextStepAnalysis",
    "analyze_strategic_next_steps",
]
