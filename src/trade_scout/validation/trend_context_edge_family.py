"""Canonical-only T0-T5 trend-context research family.

This validation-layer module decomposes the first-program trend baseline without requiring the T6
market benchmark. It keeps the dataset, universe, horizon, entry semantics, stride and numerical
lookbacks fixed, then compares each child trend context with its predeclared parent context.
Inference is exploratory: calendar-month clustering is used for uncertainty, sign-flip randomization
is used for the child-vs-parent null, and Benjamini-Hochberg is applied across T1-T5.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from random import Random
from statistics import fmean, median

from trade_scout.data.contracts import ResearchBar
from trade_scout.features.trend_context import (
    TrendContext,
    TrendContextConfig,
    qualifying_trend_indices,
)
from trade_scout.outcomes.trend_baseline import (
    TrendBaselineOutcome,
    measure_trend_baseline_outcomes,
)
from trade_scout.validation.multiplicity import (
    HypothesisFamily,
    MultiplicityMethod,
    adjust_p_values,
)

_CONTEXTS = (
    TrendContext.T0,
    TrendContext.T1,
    TrendContext.T2,
    TrendContext.T3,
    TrendContext.T4,
    TrendContext.T5,
)
_PARENT = {
    TrendContext.T1: TrendContext.T0,
    TrendContext.T2: TrendContext.T1,
    TrendContext.T3: TrendContext.T1,
    TrendContext.T4: TrendContext.T3,
    TrendContext.T5: TrendContext.T2,
}


@dataclass(frozen=True, slots=True)
class Interval:
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class TrendContextReadout:
    context: TrendContext
    parent_context: TrendContext | None
    sample_size: int
    mean_return: float
    median_return: float
    win_rate: float
    profit_factor: float | None
    median_mfe: float
    median_mae: float
    mean_interval: Interval
    parent_mean_return: float | None
    paired_month_excess: float | None
    paired_month_excess_interval: Interval | None
    raw_parent_randomization_p_value: float | None
    adjusted_parent_randomization_p_value: float | None
    preliminary_gate_passed: bool
    gate_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrendContextFamilyVerdict:
    code: str
    headline: str
    explanation: str


@dataclass(frozen=True, slots=True)
class TrendContextEdgeFamilyReport:
    universe_id: str
    universe_label: str
    dataset_version: str
    analysis_start: date
    analysis_end: date
    horizon: int
    sampling_stride: int
    trend_config: TrendContextConfig
    context_results: tuple[TrendContextReadout, ...]
    multiplicity_family_id: str
    multiplicity_method: MultiplicityMethod
    alpha: float
    candidate_contexts: tuple[TrendContext, ...]
    verdict: TrendContextFamilyVerdict
    bootstrap_resamples: int
    randomization_iterations: int
    random_seed: int
    research_state: str = "EXPLORATORY"
    t6_market_benchmark_status: str = "NOT_RUN"
    broader_research_family_correction_status: str = "NOT_RUN"
    out_of_sample_status: str = "NOT_RUN"
    report_definition_version: str = "trend-context-edge-family-v0.1"


@dataclass(frozen=True, slots=True)
class _ProvisionalReadout:
    sample_size: int
    mean_return: float
    median_return: float
    win_rate: float
    profit_factor: float | None
    median_mfe: float
    median_mae: float
    mean_interval: Interval
    parent: TrendContext | None
    parent_mean: float | None
    paired_excess: float | None
    paired_interval: Interval | None
    raw_p: float | None


def build_trend_context_edge_family_report(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    universe_id: str,
    universe_label: str,
    analysis_start: date,
    analysis_end: date,
    horizon: int = 20,
    sampling_stride: int = 5,
    sma_slope_lookback: int = 20,
    trailing_return_intervals: int = 60,
    relative_strength_intervals: int = 60,
    bootstrap_resamples: int = 2_000,
    randomization_iterations: int = 10_000,
    random_seed: int = 20260817,
    alpha: float = 0.05,
    progress: Callable[[str], None] | None = None,
) -> TrendContextEdgeFamilyReport:
    """Evaluate T0-T5 on one immutable canonical fixed cohort without provider calls."""

    _validate_inputs(
        series_by_symbol,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        horizon=horizon,
        sampling_stride=sampling_stride,
        bootstrap_resamples=bootstrap_resamples,
        randomization_iterations=randomization_iterations,
        alpha=alpha,
    )
    config = TrendContextConfig(
        sma_200_period=200,
        sma_50_period=50,
        sma_slope_lookback=sma_slope_lookback,
        trailing_return_intervals=trailing_return_intervals,
        relative_strength_intervals=relative_strength_intervals,
    )

    outcomes_by_context: dict[TrendContext, tuple[TrendBaselineOutcome, ...]] = {}
    for position, context in enumerate(_CONTEXTS, start=1):
        _emit(progress, f"[{position}/{len(_CONTEXTS)}] evaluating {context.value}")
        collected: list[TrendBaselineOutcome] = []
        for bars in series_by_symbol.values():
            indices = qualifying_trend_indices(bars, context=context, config=config)
            selected = tuple(
                index
                for index in indices
                if analysis_start <= bars[index].trade_date <= analysis_end
            )
            measured = measure_trend_baseline_outcomes(
                bars,
                selected,
                horizons=(horizon,),
                stride=sampling_stride,
            )
            collected.extend(
                item for item in measured if date.fromisoformat(item.exit_date) <= analysis_end
            )
        outcomes = tuple(collected)
        if not outcomes:
            raise ValueError(f"trend context {context.value} has no complete outcomes")
        outcomes_by_context[context] = outcomes
        _emit(
            progress,
            f"    n={len(outcomes)} | mean={fmean(item.forward_return for item in outcomes):+.3%}",
        )

    raw_p_values: dict[str, float] = {}
    provisional: dict[TrendContext, _ProvisionalReadout] = {}
    for context in _CONTEXTS:
        outcomes = outcomes_by_context[context]
        returns = tuple(item.forward_return for item in outcomes)
        parent = _PARENT.get(context)
        parent_outcomes = outcomes_by_context[parent] if parent is not None else None
        parent_mean = (
            fmean(item.forward_return for item in parent_outcomes)
            if parent_outcomes is not None
            else None
        )
        paired_excess: float | None = None
        paired_interval: Interval | None = None
        raw_p: float | None = None
        if parent_outcomes is not None:
            differences = _paired_month_differences(outcomes, parent_outcomes)
            if not differences:
                raise ValueError(
                    f"trend context {context.value} shares no complete calendar months with parent"
                )
            paired_excess = fmean(differences)
            paired_interval = _bootstrap_scalar_interval(
                differences,
                resamples=bootstrap_resamples,
                seed=random_seed + 1000 + int(context.value[1:]),
            )
            raw_p = _sign_flip_p_value(
                differences,
                iterations=randomization_iterations,
                seed=random_seed + 2000 + int(context.value[1:]),
            )
            raw_p_values[_hypothesis_id(context)] = raw_p

        provisional[context] = _ProvisionalReadout(
            sample_size=len(outcomes),
            mean_return=fmean(returns),
            median_return=median(returns),
            win_rate=sum(value > 0 for value in returns) / len(returns),
            profit_factor=_profit_factor(returns),
            median_mfe=median(item.mfe for item in outcomes),
            median_mae=median(item.mae for item in outcomes),
            mean_interval=_month_cluster_mean_interval(
                outcomes,
                resamples=bootstrap_resamples,
                seed=random_seed + 100 + int(context.value[1:]),
            ),
            parent=parent,
            parent_mean=parent_mean,
            paired_excess=paired_excess,
            paired_interval=paired_interval,
            raw_p=raw_p,
        )

    family = HypothesisFamily(
        family_id="first-program-A-T1-T5-parent-increment-family-v0.1",
        hypothesis_ids=tuple(_hypothesis_id(context) for context in _CONTEXTS[1:]),
        method=MultiplicityMethod.BENJAMINI_HOCHBERG,
        alpha=alpha,
    )
    adjusted = {
        item.hypothesis_id: item.adjusted_p_value
        for item in adjust_p_values(family, raw_p_values)
    }

    results: list[TrendContextReadout] = []
    for context in _CONTEXTS:
        values = provisional[context]
        adjusted_p = (
            adjusted.get(_hypothesis_id(context)) if values.parent is not None else None
        )
        failures = (
            _gate_failures(
                mean_interval=values.mean_interval,
                paired_excess=values.paired_excess,
                paired_interval=values.paired_interval,
                adjusted_p=adjusted_p,
                alpha=alpha,
            )
            if values.parent is not None
            else ()
        )
        results.append(
            TrendContextReadout(
                context=context,
                parent_context=values.parent,
                sample_size=values.sample_size,
                mean_return=values.mean_return,
                median_return=values.median_return,
                win_rate=values.win_rate,
                profit_factor=values.profit_factor,
                median_mfe=values.median_mfe,
                median_mae=values.median_mae,
                mean_interval=values.mean_interval,
                parent_mean_return=values.parent_mean,
                paired_month_excess=values.paired_excess,
                paired_month_excess_interval=values.paired_interval,
                raw_parent_randomization_p_value=values.raw_p,
                adjusted_parent_randomization_p_value=adjusted_p,
                preliminary_gate_passed=values.parent is not None and not failures,
                gate_failures=failures,
            )
        )

    readouts = tuple(results)
    candidates = tuple(item.context for item in readouts if item.preliminary_gate_passed)
    verdict = _verdict(candidates)
    _emit(
        progress,
        f"family complete: {len(candidates)} context(s) clear the preliminary parent-increment gate",
    )

    first_series = next(iter(series_by_symbol.values()))
    return TrendContextEdgeFamilyReport(
        universe_id=universe_id,
        universe_label=universe_label,
        dataset_version=str(first_series[0].dataset_version),
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        horizon=horizon,
        sampling_stride=sampling_stride,
        trend_config=config,
        context_results=readouts,
        multiplicity_family_id=family.family_id,
        multiplicity_method=family.method,
        alpha=alpha,
        candidate_contexts=candidates,
        verdict=verdict,
        bootstrap_resamples=bootstrap_resamples,
        randomization_iterations=randomization_iterations,
        random_seed=random_seed,
    )


def _paired_month_differences(
    child: tuple[TrendBaselineOutcome, ...],
    parent: tuple[TrendBaselineOutcome, ...],
) -> tuple[float, ...]:
    child_months = _monthly_returns(child)
    parent_months = _monthly_returns(parent)
    common = tuple(sorted(set(child_months) & set(parent_months)))
    return tuple(fmean(child_months[key]) - fmean(parent_months[key]) for key in common)


def _monthly_returns(
    outcomes: tuple[TrendBaselineOutcome, ...],
) -> dict[str, tuple[float, ...]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for item in outcomes:
        grouped[item.signal_date[:7]].append(item.forward_return)
    return {key: tuple(values) for key, values in grouped.items()}


def _month_cluster_mean_interval(
    outcomes: tuple[TrendBaselineOutcome, ...],
    *,
    resamples: int,
    seed: int,
) -> Interval:
    months = _monthly_returns(outcomes)
    keys = tuple(sorted(months))
    rng = Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sampled: list[float] = []
        for _ in keys:
            sampled.extend(months[rng.choice(keys)])
        estimates.append(fmean(sampled))
    return _percentile_interval(estimates)


def _bootstrap_scalar_interval(
    values: tuple[float, ...],
    *,
    resamples: int,
    seed: int,
) -> Interval:
    rng = Random(seed)
    estimates = [fmean(rng.choice(values) for _ in values) for _ in range(resamples)]
    return _percentile_interval(estimates)


def _sign_flip_p_value(
    differences: tuple[float, ...],
    *,
    iterations: int,
    seed: int,
) -> float:
    observed = fmean(differences)
    rng = Random(seed)
    null = []
    for _ in range(iterations):
        null.append(fmean(value if rng.random() < 0.5 else -value for value in differences))
    return (sum(value >= observed for value in null) + 1) / (iterations + 1)


def _percentile_interval(values: list[float]) -> Interval:
    ordered = sorted(values)
    lower_index = max(0, int(0.025 * (len(ordered) - 1)))
    upper_index = min(len(ordered) - 1, int(0.975 * (len(ordered) - 1)))
    return Interval(ordered[lower_index], ordered[upper_index])


def _profit_factor(returns: tuple[float, ...]) -> float | None:
    gains = sum(value for value in returns if value > 0)
    losses = -sum(value for value in returns if value < 0)
    if losses == 0:
        return None
    return gains / losses


def _gate_failures(
    *,
    mean_interval: Interval,
    paired_excess: float | None,
    paired_interval: Interval | None,
    adjusted_p: float | None,
    alpha: float,
) -> tuple[str, ...]:
    failures: list[str] = []
    if mean_interval.lower <= 0:
        failures.append("RAW_MEAN_CI_INCLUDES_ZERO")
    if paired_excess is None or paired_excess <= 0:
        failures.append("NON_POSITIVE_PARENT_INCREMENT")
    if paired_interval is None or paired_interval.lower <= 0:
        failures.append("PARENT_INCREMENT_CI_INCLUDES_ZERO")
    if adjusted_p is None or adjusted_p >= alpha:
        failures.append("PARENT_INCREMENT_NOT_SIGNIFICANT_AFTER_BH")
    return tuple(failures)


def _verdict(candidates: tuple[TrendContext, ...]) -> TrendContextFamilyVerdict:
    if candidates:
        names = ", ".join(item.value for item in candidates)
        return TrendContextFamilyVerdict(
            code="PRELIMINARY_TREND_COMPONENT_EDGE",
            headline="At least one trend component adds measurable continuation over its parent rule.",
            explanation=(
                f"Candidate context(s): {names}. This is exploratory fixed-cohort evidence only; "
                "T6 market-relative strength, broader family correction and out-of-sample validation "
                "remain incomplete."
            ),
        )
    return TrendContextFamilyVerdict(
        code="NO_TREND_COMPONENT_CLEARS_PRELIMINARY_GATE",
        headline="No T1-T5 trend component establishes a preliminary incremental continuation edge.",
        explanation=(
            "None of the child trend rules simultaneously has a positive clustered raw-return "
            "interval, positive parent-context increment, positive parent-increment interval and "
            "BH-adjusted parent-randomization significance."
        ),
    )


def _hypothesis_id(context: TrendContext) -> str:
    return f"trend-parent-increment:{context.value}"


def _validate_inputs(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    analysis_start: date,
    analysis_end: date,
    horizon: int,
    sampling_stride: int,
    bootstrap_resamples: int,
    randomization_iterations: int,
    alpha: float,
) -> None:
    if not series_by_symbol:
        raise ValueError("trend context family requires at least one instrument series")
    if analysis_end < analysis_start:
        raise ValueError("analysis_end must be on or after analysis_start")
    if horizon < 1 or sampling_stride < 1:
        raise ValueError("horizon and sampling_stride must be positive")
    if bootstrap_resamples < 100:
        raise ValueError("bootstrap_resamples must be at least 100")
    if randomization_iterations < 100:
        raise ValueError("randomization_iterations must be at least 100")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


__all__ = [
    "Interval",
    "TrendContextEdgeFamilyReport",
    "TrendContextFamilyVerdict",
    "TrendContextReadout",
    "build_trend_context_edge_family_report",
]
