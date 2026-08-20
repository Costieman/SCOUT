# ruff: noqa: E501
"""Deterministic, evidence-grounded next-experiment suggestions for Strategy Builder runs.

This module does not predict profitability or select a trading strategy. It reads already-computed
exit-policy summaries and translates visible parameter-shape evidence into explicit research
hypotheses and bounded next experiments.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from trade_scout.risk.exit_policies import ExitFamily
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
    version: str = "strategy-next-step-v0.1"


def analyze_strategic_next_steps(
    comparison: ExitResearchComparison,
) -> StrategicNextStepAnalysis:
    """Infer directional research options without treating exploratory evidence as advice."""

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

    family, points = _largest_sweep_family(managed)
    if family is not None and len(points) >= 3:
        shape = _shape(points)
        if family is ExitFamily.FIXED_PERCENT_STOP:
            return _fixed_stop_analysis(comparison, hold, points, shape)

    best = max(
        managed, key=lambda item: item.expectancy if item.expectancy is not None else float("-inf")
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
            f"{_pct(best.expectancy)}, but the available rows do not form a sufficiently clean "
            f"single-family sweep. {hold_text}"
        ),
        caution=_caution(comparison),
        options=(
            StrategicExperimentOption(
                title="Run a cleaner local sweep",
                direction="Hold the entry population and every partner exit parameter fixed.",
                proposed_range="Choose one exit dimension and test at least 5 ordered values around the current best row.",
                rationale="A single-variable shape is easier to interpret than a mixed policy grid.",
                falsifier="If neighboring values do not reproduce the apparent advantage, treat the current best row as unstable.",
            ),
        ),
    )


def _fixed_stop_analysis(
    comparison: ExitResearchComparison,
    hold: ExitPolicySummary | None,
    points: tuple[ExitPolicySummary, ...],
    shape: str,
) -> StrategicNextStepAnalysis:
    ordered = tuple(sorted(points, key=lambda item: item.resolved_parameters["distance_pct"]))
    first = ordered[0]
    last = ordered[-1]
    min_pct = first.resolved_parameters["distance_pct"] * 100.0
    max_pct = last.resolved_parameters["distance_pct"] * 100.0
    best = max(
        ordered, key=lambda item: item.expectancy if item.expectancy is not None else float("-inf")
    )
    hold_gap = (
        None
        if hold is None or hold.expectancy is None or best.expectancy is None
        else best.expectancy - hold.expectancy
    )

    if shape == "increasing" and best is last:
        wider_high = min(95.0, max(50.0, max_pct * 2.0))
        observation = (
            f"Expectancy rises across the tested fixed-stop range from {_pct(first.expectancy)} at "
            f"{min_pct:g}% to {_pct(last.expectancy)} at {max_pct:g}%, while stop-outs fall from "
            f"{_prob(first.stop_out_rate)} to {_prob(last.stop_out_rate)}. The best tested value is "
            "the upper boundary, so the present sweep is boundary-limited rather than showing an interior optimum."
        )
        if hold_gap is not None and hold_gap < 0:
            observation += (
                f" Even the best managed row remains {_pp(abs(hold_gap))} below the hold control."
            )
        return StrategicNextStepAnalysis(
            headline="Wider stops are the strongest next direction; also test a separate ultra-tight regime.",
            observation=observation,
            caution=_caution(comparison),
            options=(
                StrategicExperimentOption(
                    title="Extend the wide-stop branch",
                    direction="Move outward in the same direction as the observed expectancy gradient.",
                    proposed_range=f"Test approximately {max_pct:g}% to {wider_high:g}% fixed stops; start with 5-point steps, then tighten around any plateau or reversal.",
                    rationale="The current best value sits at the edge of the tested range, so the experiment has not yet located the turning point.",
                    falsifier="Stop extending once expectancy plateaus or falls across adjacent values, or downside/tail metrics deteriorate enough to erase the risk-control benefit.",
                ),
                StrategicExperimentOption(
                    title="Probe the cut-losers-immediately branch",
                    direction="Test the opposite regime rather than assuming the current monotonic shape continues below the tested minimum.",
                    proposed_range=f"Test 1% to {min(5.0, min_pct):g}% fixed stops in 1-point steps.",
                    rationale="A very tight stop may behave discontinuously by rejecting weak entries quickly while allowing a small runner population to survive; the current grid cannot test that hypothesis if it starts at 5% or wider.",
                    falsifier="Reject this branch if very tight stops collapse expectancy, materially worsen gap/slippage sensitivity, or fail to produce a distinct runner distribution.",
                ),
            ),
        )

    if shape == "decreasing" and best is first:
        low = max(0.5, min_pct / 4.0)
        return StrategicNextStepAnalysis(
            headline="Tighter stops are the strongest next direction.",
            observation=(
                f"Expectancy declines as the fixed stop widens from {min_pct:g}% to {max_pct:g}%, "
                f"with the best tested row at the lower boundary ({_pct(first.expectancy)})."
            ),
            caution=_caution(comparison),
            options=(
                StrategicExperimentOption(
                    title="Extend below the current minimum",
                    direction="Move toward faster loss rejection.",
                    proposed_range=f"Test approximately {low:g}% to {min_pct:g}% fixed stops with finer spacing near the current boundary.",
                    rationale="The optimum, if real, may lie below the tested range because the current best value is boundary-limited.",
                    falsifier="Reject the tighter-stop branch if expectancy reverses downward or gap/slippage sensitivity becomes dominant.",
                ),
            ),
        )

    best_pct = best.resolved_parameters["distance_pct"] * 100.0
    radius = max(1.0, best_pct * 0.2)
    return StrategicNextStepAnalysis(
        headline="The sweep shows an interior or non-monotonic region worth resolving locally.",
        observation=(
            f"The strongest fixed-stop row is around {best_pct:g}% at {_pct(best.expectancy)} rather than a clean boundary optimum."
        ),
        caution=_caution(comparison),
        options=(
            StrategicExperimentOption(
                title="Resolve the local optimum",
                direction="Increase parameter resolution around the strongest neighborhood.",
                proposed_range=f"Test roughly {max(0.5, best_pct - radius):g}% to {min(95.0, best_pct + radius):g}% with smaller steps.",
                rationale="Broad sweeps locate regions; a local sweep tests whether the apparent peak is stable across neighboring values.",
                falsifier="Treat the peak as unstable if adjacent values do not retain similar expectancy and downside characteristics.",
            ),
        ),
    )


def _largest_sweep_family(
    managed: tuple[ExitPolicySummary, ...],
) -> tuple[ExitFamily | None, tuple[ExitPolicySummary, ...]]:
    groups: dict[ExitFamily, list[ExitPolicySummary]] = {}
    for item in managed:
        if item.target_family is not None:
            continue
        parameter = _primary_parameter(item)
        if parameter is None:
            continue
        groups.setdefault(item.family, []).append(item)
    if not groups:
        return None, ()
    family = max(groups, key=lambda value: len(groups[value]))
    points = tuple(groups[family])
    if len({_primary_parameter(item) for item in points}) != len(points):
        return None, ()
    return family, points


def _primary_parameter(item: ExitPolicySummary) -> float | None:
    if item.family in {ExitFamily.FIXED_PERCENT_STOP, ExitFamily.TRAILING_PERCENT_STOP}:
        return item.resolved_parameters.get("distance_pct")
    if item.family in {ExitFamily.ATR_STOP, ExitFamily.TRAILING_ATR_STOP}:
        return item.resolved_parameters.get("atr_multiple")
    return None


def _shape(points: tuple[ExitPolicySummary, ...]) -> str:
    ordered = tuple(sorted(points, key=lambda item: _primary_parameter(item) or 0.0))
    expectations = tuple(item.expectancy for item in ordered)
    if any(value is None for value in expectations):
        return "mixed"
    values = tuple(float(value) for value in expectations if value is not None)
    diffs = tuple(right - left for left, right in pairwise(values))
    tolerance = 1e-12
    rising = sum(diff >= -tolerance for diff in diffs)
    falling = sum(diff <= tolerance for diff in diffs)
    threshold = max(1, int(0.8 * len(diffs) + 0.999999))
    if rising >= threshold and values[-1] > values[0]:
        return "increasing"
    if falling >= threshold and values[-1] < values[0]:
        return "decreasing"
    return "mixed"


def _caution(comparison: ExitResearchComparison) -> str:
    return (
        f"Exploratory only: {comparison.complete_event_count} complete events on one frozen historical "
        "population. A directional next experiment is a hypothesis, not a validated trading recommendation; "
        "out-of-sample testing, multiplicity control, execution sensitivity, and portfolio constraints still matter."
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:+.2f}%"


def _prob(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _pp(value: float) -> str:
    return f"{value * 100:.2f} percentage points"


__all__ = [
    "StrategicExperimentOption",
    "StrategicNextStepAnalysis",
    "analyze_strategic_next_steps",
]
