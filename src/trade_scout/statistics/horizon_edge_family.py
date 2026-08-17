"""Controlled holding-horizon research family for readable market-wide edge analysis.

This module keeps the strategy definition fixed and changes only the forward holding horizon. It
reuses the readable-edge observation, bootstrap, and randomized-timing machinery, then applies a
Benjamini-Hochberg correction across the predeclared horizon family. The result is exploratory
research evidence, not an automatic promotion decision.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from statistics import fmean

from trade_scout.data.contracts import ResearchBar
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig
from trade_scout.patterns.timeframes import PatternTimeframe
from trade_scout.statistics.readable_edge import (
    BaselineComparison,
    PerformanceReadout,
    RandomTimingControl,
    _observation_sets,
    _paired_month_difference_interval,
    _performance,
    _random_timing_control,
)
from trade_scout.validation.multiplicity import (
    HypothesisFamily,
    MultiplicityMethod,
    adjust_p_values,
)


@dataclass(frozen=True, slots=True)
class HorizonEdgeReadout:
    """One fixed-horizon result inside the predeclared horizon research family."""

    horizon: int
    performance: PerformanceReadout
    simple_baseline: BaselineComparison
    randomized_timing: RandomTimingControl
    adjusted_random_timing_p_value: float
    preliminary_gate_passed: bool
    gate_failures: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HorizonFamilyVerdict:
    """Plain-language diagnostic for the horizon family without changing research state."""

    code: str
    headline: str
    explanation: str


@dataclass(frozen=True, slots=True)
class HorizonEdgeFamilyReport:
    """Exploratory family-level evidence with explicit multiplicity accounting."""

    universe_id: str
    universe_label: str
    dataset_version: str
    analysis_start: date
    analysis_end: date
    pattern_timeframe: PatternTimeframe
    selected_config: ConsolidationBreakoutConfig
    horizon_family: tuple[int, ...]
    horizon_results: tuple[HorizonEdgeReadout, ...]
    multiplicity_family_id: str
    multiplicity_method: MultiplicityMethod
    alpha: float
    candidate_horizons: tuple[int, ...]
    lowest_adjusted_p_horizon: int
    best_observed_random_excess_horizon: int
    verdict: HorizonFamilyVerdict
    bootstrap_resamples: int
    random_iterations: int
    random_seed: int
    research_state: str = "EXPLORATORY"
    broader_research_family_correction_status: str = "NOT_RUN"
    out_of_sample_status: str = "NOT_RUN"
    report_definition_version: str = "horizon-edge-family-v0.1"


def build_horizon_edge_family_report(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    universe_id: str,
    universe_label: str,
    config: ConsolidationBreakoutConfig,
    analysis_start: date,
    analysis_end: date,
    pattern_timeframe: PatternTimeframe = PatternTimeframe.DAILY,
    horizons: tuple[int, ...] = (2, 3, 5, 10, 20, 40, 60),
    bootstrap_resamples: int = 2_000,
    random_iterations: int = 1_000,
    random_seed: int = 20260817,
    alpha: float = 0.05,
    progress: Callable[[str], None] | None = None,
) -> HorizonEdgeFamilyReport:
    """Evaluate one fixed strategy across a predeclared family of holding horizons.

    The only research dimension changed here is the daily-session holding horizon.
    Randomized-timing p-values are corrected across the complete supplied horizon family. This does
    not correct for other strategy, timeframe, trend, duration, tightness, volume, stop, or regime
    searches.
    """

    _validate_inputs(
        series_by_symbol,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        horizons=horizons,
        bootstrap_resamples=bootstrap_resamples,
        random_iterations=random_iterations,
        alpha=alpha,
    )
    ordered_horizons = tuple(horizons)
    raw: list[tuple[int, PerformanceReadout, BaselineComparison, RandomTimingControl]] = []

    for position, horizon in enumerate(ordered_horizons, start=1):
        _emit(
            progress,
            f"[{position}/{len(ordered_horizons)}] evaluating {horizon}-session horizon",
        )
        strategy, baseline, random_candidates = _observation_sets(
            series_by_symbol,
            config=config,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            pattern_timeframe=pattern_timeframe,
            selected_horizon=horizon,
        )
        if not strategy:
            raise ValueError(f"horizon {horizon} has no complete strategy outcomes")

        seed_offset = horizon * 10_000
        performance = _performance(
            strategy,
            resamples=bootstrap_resamples,
            seed=random_seed + seed_offset,
        )
        baseline_mean = fmean(item.forward_return for item in baseline) if baseline else None
        simple_baseline = BaselineComparison(
            comparator_id="simple-trend-context-baseline-v0.1",
            comparator_description=_baseline_description(pattern_timeframe),
            sample_size=len(baseline),
            mean_return=baseline_mean,
            excess_mean_return=(
                performance.mean_return - baseline_mean if baseline_mean is not None else None
            ),
            excess_interval=_paired_month_difference_interval(
                strategy,
                baseline,
                resamples=bootstrap_resamples,
                seed=random_seed + seed_offset + 1,
            ),
        )
        randomized = _random_timing_control(
            strategy,
            random_candidates,
            iterations=random_iterations,
            seed=random_seed + seed_offset + 2,
        )
        raw.append((horizon, performance, simple_baseline, randomized))
        _emit(
            progress,
            (
                f"    raw={performance.mean_return:+.3%} | "
                f"baseline excess={_pct(simple_baseline.excess_mean_return)} | "
                f"random excess={randomized.excess_vs_null_mean:+.3%} | "
                f"raw p={randomized.one_sided_p_value:.4f}"
            ),
        )

    family_id = "consolidation-breakout-holding-horizon-family-v0.1"
    hypothesis_ids = tuple(_hypothesis_id(horizon) for horizon in ordered_horizons)
    family = HypothesisFamily(
        family_id=family_id,
        hypothesis_ids=hypothesis_ids,
        method=MultiplicityMethod.BENJAMINI_HOCHBERG,
        alpha=alpha,
    )
    adjusted = {
        item.hypothesis_id: item.adjusted_p_value
        for item in adjust_p_values(
            family,
            {
                _hypothesis_id(horizon): randomized.one_sided_p_value
                for horizon, _, _, randomized in raw
            },
        )
    }

    results: list[HorizonEdgeReadout] = []
    for horizon, performance, simple_baseline, randomized in raw:
        adjusted_p = adjusted[_hypothesis_id(horizon)]
        failures = _gate_failures(
            performance,
            simple_baseline,
            randomized,
            adjusted_p_value=adjusted_p,
            alpha=alpha,
        )
        results.append(
            HorizonEdgeReadout(
                horizon=horizon,
                performance=performance,
                simple_baseline=simple_baseline,
                randomized_timing=randomized,
                adjusted_random_timing_p_value=adjusted_p,
                preliminary_gate_passed=not failures,
                gate_failures=failures,
            )
        )

    readouts = tuple(results)
    candidates = tuple(item.horizon for item in readouts if item.preliminary_gate_passed)
    lowest_adjusted = min(
        readouts,
        key=lambda item: (item.adjusted_random_timing_p_value, item.horizon),
    )
    best_random_excess = max(
        readouts,
        key=lambda item: (item.randomized_timing.excess_vs_null_mean, -item.horizon),
    )
    verdict = _verdict(candidates)
    _emit(
        progress,
        (
            "family complete: "
            f"{len(candidates)} horizon(s) clear the preliminary family gate; "
            f"lowest BH-adjusted p={lowest_adjusted.adjusted_random_timing_p_value:.4f} "
            f"at {lowest_adjusted.horizon} sessions"
        ),
    )

    first_series = next(iter(series_by_symbol.values()))
    return HorizonEdgeFamilyReport(
        universe_id=universe_id,
        universe_label=universe_label,
        dataset_version=str(first_series[0].dataset_version),
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        pattern_timeframe=pattern_timeframe,
        selected_config=config,
        horizon_family=ordered_horizons,
        horizon_results=readouts,
        multiplicity_family_id=family_id,
        multiplicity_method=family.method,
        alpha=alpha,
        candidate_horizons=candidates,
        lowest_adjusted_p_horizon=lowest_adjusted.horizon,
        best_observed_random_excess_horizon=best_random_excess.horizon,
        verdict=verdict,
        bootstrap_resamples=bootstrap_resamples,
        random_iterations=random_iterations,
        random_seed=random_seed,
    )


def _gate_failures(
    performance: PerformanceReadout,
    simple_baseline: BaselineComparison,
    randomized: RandomTimingControl,
    *,
    adjusted_p_value: float,
    alpha: float,
) -> tuple[str, ...]:
    failures: list[str] = []
    if simple_baseline.excess_mean_return is None or simple_baseline.excess_mean_return <= 0:
        failures.append("NON_POSITIVE_BASELINE_EXCESS")
    if randomized.excess_vs_null_mean <= 0:
        failures.append("NON_POSITIVE_RANDOM_TIMING_EXCESS")
    if adjusted_p_value >= alpha:
        failures.append("RANDOM_TIMING_NOT_SIGNIFICANT_AFTER_BH")
    if performance.mean_interval is None or performance.mean_interval.lower <= 0:
        failures.append("RAW_MEAN_CI_INCLUDES_ZERO")
    return tuple(failures)


def _verdict(candidate_horizons: tuple[int, ...]) -> HorizonFamilyVerdict:
    if candidate_horizons:
        formatted = ", ".join(str(value) for value in candidate_horizons)
        return HorizonFamilyVerdict(
            code="PRELIMINARY_HORIZON_EDGE",
            headline="At least one holding horizon clears the preliminary horizon-family gate.",
            explanation=(
                f"Candidate horizon(s): {formatted} sessions. This clears the horizon-family "
                "baseline, randomized-timing, clustered-uncertainty and BH multiplicity "
                "checks only. Broader strategy-family correction and out-of-sample validation "
                "remain required."
            ),
        )
    return HorizonFamilyVerdict(
        code="NO_HORIZON_CLEARS_PRELIMINARY_GATE",
        headline="No tested holding horizon establishes a preliminary incremental edge.",
        explanation=(
            "None of the predeclared horizons simultaneously beats the current trend-context "
            "baseline, shows positive randomized-timing excess with BH-adjusted significance, "
            "and has a positive month-clustered raw-mean confidence interval."
        ),
    )


def _baseline_description(pattern_timeframe: PatternTimeframe) -> str:
    return (
        f"same-instrument {pattern_timeframe.value} trend-context bars sampled every 5 "
        "pattern bars; outcomes measured in daily trading sessions"
    )


def _hypothesis_id(horizon: int) -> str:
    return f"holding-horizon:{horizon}"


def _validate_inputs(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    analysis_start: date,
    analysis_end: date,
    horizons: tuple[int, ...],
    bootstrap_resamples: int,
    random_iterations: int,
    alpha: float,
) -> None:
    if not series_by_symbol:
        raise ValueError("horizon family requires at least one instrument series")
    if analysis_end < analysis_start:
        raise ValueError("analysis_end must be on or after analysis_start")
    if not horizons or any(value < 1 for value in horizons):
        raise ValueError("horizons must contain positive session counts")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must be unique")
    if bootstrap_resamples < 100:
        raise ValueError("bootstrap_resamples must be at least 100")
    if random_iterations < 100:
        raise ValueError("random_iterations must be at least 100")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    for symbol, bars in series_by_symbol.items():
        if not symbol.strip() or not bars:
            raise ValueError("horizon family symbols must be non-empty and contain data")


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.3%}"


def _emit(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)


__all__ = [
    "HorizonEdgeFamilyReport",
    "HorizonEdgeReadout",
    "HorizonFamilyVerdict",
    "build_horizon_edge_family_report",
]
