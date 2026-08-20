# ruff: noqa: E501
"""Deterministic interpretation of one-variable Strategy Builder response surfaces.

The analyzer deliberately separates descriptive evidence from recommendation. It looks for broad
shape, local robustness, sample-size changes and supporting secondary metrics, then proposes the
next bounded experiment. It never mutates a strategy, launches a run, or calls an external model.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from statistics import median


@dataclass(frozen=True, slots=True)
class ParameterEvidencePoint:
    """Comparable evidence at one value of a single research parameter."""

    value: float
    sample_size: int
    expectancy: float | None
    win_probability: float | None = None
    profit_factor: float | None = None
    tail_loss_p05: float | None = None
    average_holding_period_sessions: float | None = None
    stop_out_rate: float | None = None
    target_hit_rate: float | None = None


@dataclass(frozen=True, slots=True)
class ParameterExperimentOption:
    """One evidence-grounded next experiment."""

    title: str
    direction: str
    proposed_range: str
    rationale: str
    falsifier: str


@dataclass(frozen=True, slots=True)
class ParameterSurfaceAnalysis:
    """Plain-English interpretation of one one-dimensional response surface."""

    headline: str
    observation: str
    robustness: str
    caution: str
    options: tuple[ParameterExperimentOption, ...]
    shape: str
    version: str = "parameter-surface-analysis-v0.1"


def analyze_parameter_surface(
    *,
    parameter_label: str,
    unit_label: str,
    points: tuple[ParameterEvidencePoint, ...],
    control_expectancy: float | None = None,
    special_ultra_tight_stop_branch: bool = False,
) -> ParameterSurfaceAnalysis:
    """Interpret a one-variable surface without promoting a historical winner as an optimum."""

    usable = tuple(
        sorted(
            (item for item in points if item.expectancy is not None),
            key=lambda item: item.value,
        )
    )
    if len(usable) < 3:
        return ParameterSurfaceAnalysis(
            headline=f"Not enough {parameter_label} values for directional analysis.",
            observation="At least three complete parameter cells are required before SCOUT infers a response-surface direction.",
            robustness="No local robustness assessment is available yet.",
            caution=_caution(usable),
            options=(),
            shape="insufficient",
        )

    best = max(usable, key=lambda item: float(item.expectancy or float("-inf")))
    first, last = usable[0], usable[-1]
    shape = _shape(usable)
    plateau = _plateau(usable, best)
    metric_support = _secondary_metric_support(usable, best)
    count_note = _sample_size_note(usable, best)
    control_note = _control_note(best, control_expectancy)
    unit = _unit_suffix(unit_label)

    observation = (
        f"{parameter_label} was tested from {_value(first.value, unit)} to {_value(last.value, unit)}. "
        f"Observed expectancy ranged from {_pct(min(float(item.expectancy or 0.0) for item in usable))} to {_pct(float(best.expectancy or 0.0))}; "
        f"the strongest tested cell was {_value(best.value, unit)}. {control_note} {count_note}"
    )

    robustness = _robustness_text(usable, best, plateau, metric_support, unit)

    if shape == "increasing" and best is last:
        proposed = _outward_range(usable, upper=True, unit=unit)
        options = [
            ParameterExperimentOption(
                title=f"Extend the {parameter_label} range upward",
                direction="Continue in the direction of the observed expectancy gradient while keeping every other strategy component fixed.",
                proposed_range=proposed,
                rationale="The strongest cell is the upper boundary and neighboring values generally improve toward it, so the present search is boundary-limited rather than showing a resolved optimum.",
                falsifier="Stop extending when adjacent values plateau or reverse, or when secondary metrics and downside characteristics deteriorate enough that the apparent expectancy gain is no longer robust.",
            )
        ]
        if special_ultra_tight_stop_branch:
            options.append(
                ParameterExperimentOption(
                    title="Probe the ultra-tight stop regime separately",
                    direction="Test the opposite, potentially discontinuous loss-rejection regime rather than assuming the current gradient extrapolates below the tested minimum.",
                    proposed_range="Test approximately 1% to 5% fixed stops in 1 percentage-point steps.",
                    rationale="Very tight stops can create a qualitatively different population of quickly rejected trades and surviving runners; a medium-width sweep cannot establish whether that regime exists.",
                    falsifier="Reject the branch if very tight stops collapse expectancy, become dominated by gap/slippage sensitivity, or fail to produce a meaningfully different outcome distribution.",
                )
            )
        headline = f"{parameter_label}: the strongest evidence points above the tested range."
    elif shape == "decreasing" and best is first:
        options = (
            ParameterExperimentOption(
                title=f"Extend the {parameter_label} range downward",
                direction="Continue below the current lower boundary with a controlled local extension.",
                proposed_range=_outward_range(usable, upper=False, unit=unit),
                rationale="The strongest cell is the lower boundary and neighboring values generally weaken as the parameter rises.",
                falsifier="Stop extending when expectancy reverses or when the apparent gain depends on a sharply smaller sample or materially worse secondary metrics.",
            ),
        )
        headline = f"{parameter_label}: the strongest evidence points below the tested range."
    else:
        local_low, local_high = _local_range(usable, best)
        options = (
            ParameterExperimentOption(
                title=f"Resolve the {parameter_label} neighborhood",
                direction="Increase resolution around the strongest contiguous region rather than selecting the single historical maximum.",
                proposed_range=f"Test approximately {_value(local_low, unit)} to {_value(local_high, unit)} with a finer step than the current sweep.",
                rationale="An interior peak or plateau is better tested by checking whether neighboring values retain similar expectancy and supporting metrics.",
                falsifier="Treat the apparent optimum as unstable if the advantage disappears at finer resolution or is isolated to one cell while adjacent values revert materially.",
            ),
        )
        headline = (
            f"{parameter_label}: a broad robust region is more defensible than the single best cell."
            if len(plateau) >= 3
            else f"{parameter_label}: resolve the apparent interior optimum locally."
        )

    return ParameterSurfaceAnalysis(
        headline=headline,
        observation=observation,
        robustness=robustness,
        caution=_caution(usable),
        options=tuple(options),
        shape=shape,
    )


def _shape(points: tuple[ParameterEvidencePoint, ...]) -> str:
    values = tuple(float(item.expectancy or 0.0) for item in points)
    diffs = tuple(right - left for left, right in pairwise(values))
    spread = max(values) - min(values)
    tolerance = max(1e-12, spread * 0.08)
    rising = sum(diff >= -tolerance for diff in diffs)
    falling = sum(diff <= tolerance for diff in diffs)
    threshold = max(1, (4 * len(diffs) + 4) // 5)
    if rising >= threshold and values[-1] > values[0] + tolerance:
        return "increasing"
    if falling >= threshold and values[-1] < values[0] - tolerance:
        return "decreasing"
    return "mixed"


def _plateau(
    points: tuple[ParameterEvidencePoint, ...],
    best: ParameterEvidencePoint,
) -> tuple[ParameterEvidencePoint, ...]:
    values = tuple(float(item.expectancy or 0.0) for item in points)
    spread = max(values) - min(values)
    tolerance = max(0.005, spread * 0.12)
    threshold = float(best.expectancy or 0.0) - tolerance
    eligible = {item.value for item in points if float(item.expectancy or 0.0) >= threshold}
    best_index = points.index(best)
    left = best_index
    right = best_index
    while left > 0 and points[left - 1].value in eligible:
        left -= 1
    while right + 1 < len(points) and points[right + 1].value in eligible:
        right += 1
    return points[left : right + 1]


def _secondary_metric_support(
    points: tuple[ParameterEvidencePoint, ...],
    best: ParameterEvidencePoint,
) -> str:
    support: list[str] = []
    if best.win_probability is not None:
        wins = [item.win_probability for item in points if item.win_probability is not None]
        if wins and best.win_probability >= median(wins):
            support.append("win rate")
    if best.profit_factor is not None:
        factors = [item.profit_factor for item in points if item.profit_factor is not None]
        if factors and best.profit_factor >= median(factors):
            support.append("profit factor")
    if best.tail_loss_p05 is not None:
        tails = [item.tail_loss_p05 for item in points if item.tail_loss_p05 is not None]
        if tails and best.tail_loss_p05 >= median(tails):
            support.append("P05 tail outcome")
    return ", ".join(support)


def _robustness_text(
    points: tuple[ParameterEvidencePoint, ...],
    best: ParameterEvidencePoint,
    plateau: tuple[ParameterEvidencePoint, ...],
    metric_support: str,
    unit: str,
) -> str:
    if len(plateau) >= 3:
        region = f"{_value(plateau[0].value, unit)} to {_value(plateau[-1].value, unit)}"
        base = f"The best result is not isolated: {len(plateau)} contiguous cells form a near-best region from {region}. That broad region is more credible than the exact maximum at {_value(best.value, unit)}."
    elif len(plateau) == 2:
        base = "The strongest result has one neighboring cell with similar expectancy, which is more encouraging than a one-cell spike but still needs finer replication."
    else:
        base = "The strongest result is relatively isolated from its neighbors, so SCOUT treats the exact maximum as fragile until a finer local sweep reproduces it."
    if metric_support:
        base += f" Supporting secondary metrics at the best cell include {metric_support}."
    counts = [item.sample_size for item in points if item.sample_size > 0]
    if counts and best.sample_size < 0.6 * max(counts):
        base += " The best cell also has materially fewer complete observations than the largest cell, which weakens confidence in the apparent peak."
    return base


def _sample_size_note(
    points: tuple[ParameterEvidencePoint, ...], best: ParameterEvidencePoint
) -> str:
    counts = [item.sample_size for item in points if item.sample_size > 0]
    if not counts:
        return "Sample size is unavailable."
    return f"Complete-event N ranges from {min(counts):,} to {max(counts):,}; the best cell uses {best.sample_size:,}."


def _control_note(best: ParameterEvidencePoint, control_expectancy: float | None) -> str:
    if control_expectancy is None or best.expectancy is None:
        return ""
    gap = best.expectancy - control_expectancy
    if abs(gap) < 1e-12:
        return "The strongest cell matches the hold control expectancy."
    relation = "above" if gap > 0 else "below"
    return f"It is {abs(gap) * 100:.2f} percentage points {relation} the hold control."


def _outward_range(
    points: tuple[ParameterEvidencePoint, ...], *, upper: bool, unit: str
) -> str:
    ordered = tuple(sorted(points, key=lambda item: item.value))
    steps = [
        right.value - left.value for left, right in pairwise(ordered) if right.value > left.value
    ]
    step = median(steps) if steps else max(abs(ordered[-1].value) * 0.1, 1.0)
    span = max(ordered[-1].value - ordered[0].value, step * 4)
    if upper:
        low = ordered[-1].value
        high = low + max(span, step * 5)
    else:
        high = ordered[0].value
        low = max(0.0, high - max(span, step * 5))
    return f"Test approximately {_value(low, unit)} to {_value(high, unit)}, initially using steps near {_value(step, unit)} and then tighten around any plateau or reversal."


def _local_range(
    points: tuple[ParameterEvidencePoint, ...], best: ParameterEvidencePoint
) -> tuple[float, float]:
    index = points.index(best)
    left = points[max(0, index - 1)].value
    right = points[min(len(points) - 1, index + 1)].value
    if left == right:
        span = max(abs(best.value) * 0.2, 1.0)
        return max(0.0, best.value - span), best.value + span
    return left, right


def _caution(points: tuple[ParameterEvidencePoint, ...]) -> str:
    total = sum(item.sample_size for item in points)
    return (
        f"Exploratory only: {len(points)} parameter cells ({total:,} cell-level complete observations before overlap accounting). "
        "SCOUT is describing the historical surface, not proving a tradable optimum. Out-of-sample validation, multiplicity control, execution sensitivity and portfolio constraints remain required."
    )


def _unit_suffix(unit_label: str) -> str:
    lower = unit_label.lower()
    if "%" in lower or "percent" in lower:
        return "%"
    if "standard deviation" in lower:
        return "σ"
    if "atr" in lower:
        return "x ATR"
    if lower.strip() == "r" or "risk" in lower:
        return "R"
    if "trading day" in lower:
        return " trading days"
    return f" {unit_label}" if unit_label else ""


def _value(value: float, unit: str) -> str:
    return f"{value:g}{unit}"


def _pct(value: float) -> str:
    return f"{value * 100:+.2f}%"


__all__ = [
    "ParameterEvidencePoint",
    "ParameterExperimentOption",
    "ParameterSurfaceAnalysis",
    "analyze_parameter_surface",
]
