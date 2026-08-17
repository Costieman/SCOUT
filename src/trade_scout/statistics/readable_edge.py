"""Readable edge diagnostics layered on the existing market-wide research engines."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from math import sqrt
from random import Random
from statistics import fmean, median, stdev
from typing import cast

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.outcomes.forward_returns import measure_forward_outcomes
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    ConsolidationBreakoutEvent,
    detect_consolidation_breakouts,
    trend_qualified_indices,
)
from trade_scout.patterns.timeframes import (
    PatternSeriesFrame,
    PatternTimeframe,
    build_pattern_frames,
    remap_breakout_events_to_daily,
    source_index_for_pattern_index,
)
from trade_scout.statistics.timeframe_universe_research import (
    build_timeframe_universe_research_report,
)
from trade_scout.statistics.universe_research import UniverseResearchReport

_Z_95 = 1.959963984540054


@dataclass(frozen=True, slots=True)
class ReturnObservation:
    symbol: str
    signal_date: date
    forward_return: float


@dataclass(frozen=True, slots=True)
class ConfidenceInterval:
    lower: float
    upper: float
    confidence_level: float
    method: str
    cluster_count: int


@dataclass(frozen=True, slots=True)
class PerformanceReadout:
    sample_size: int
    mean_return: float
    median_return: float
    standard_deviation: float | None
    win_rate: float
    average_win: float | None
    average_loss: float | None
    payoff_ratio: float | None
    expectancy: float
    profit_factor: float | None
    minimum_return: float
    p05_return: float
    p25_return: float
    p75_return: float
    p95_return: float
    maximum_return: float
    skewness: float | None
    excess_kurtosis: float | None
    top_five_profit_share: float | None
    mean_interval: ConfidenceInterval | None
    win_rate_interval: ConfidenceInterval


@dataclass(frozen=True, slots=True)
class BaselineComparison:
    comparator_id: str
    comparator_description: str
    sample_size: int
    mean_return: float | None
    excess_mean_return: float | None
    excess_interval: ConfidenceInterval | None


@dataclass(frozen=True, slots=True)
class RandomTimingControl:
    comparator_id: str
    comparator_description: str
    iterations: int
    random_seed: int
    eligible_candidate_count: int
    matched_event_count: int
    null_mean_return: float
    null_p025: float
    null_p975: float
    excess_vs_null_mean: float
    one_sided_p_value: float


@dataclass(frozen=True, slots=True)
class CostSensitivityPoint:
    round_trip_bps: int
    net_mean_return: float


@dataclass(frozen=True, slots=True)
class ParameterRobustnessReadout:
    searched_cell_count: int
    positive_excess_cell_count: int
    positive_excess_cell_fraction: float
    selected_cell_excess: float | None
    selected_neighbor_count: int
    selected_positive_neighbor_fraction: float | None
    best_cell_duration: int | None
    best_cell_max_range_pct: float | None
    best_cell_excess: float | None


@dataclass(frozen=True, slots=True)
class EdgeVerdict:
    code: str
    headline: str
    explanation: str


@dataclass(frozen=True, slots=True)
class ReadableEdgeReport:
    source_report: UniverseResearchReport
    performance: PerformanceReadout
    simple_baseline: BaselineComparison
    randomized_timing: RandomTimingControl
    parameter_robustness: ParameterRobustnessReadout
    cost_sensitivity: tuple[CostSensitivityPoint, ...]
    break_even_round_trip_bps: float | None
    verdict: EdgeVerdict
    research_state: str = "EXPLORATORY"
    out_of_sample_status: str = "NOT_RUN"
    multiple_testing_status: str = "NOT_CORRECTED"
    portfolio_status: str = "NOT_RUN"
    report_definition_version: str = "readable-edge-v0.1"


@dataclass(frozen=True, slots=True)
class _EligibleSignal:
    stride_index: int
    daily_signal_index: int


def build_readable_edge_report(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    universe_id: str,
    universe_label: str,
    config: ConsolidationBreakoutConfig,
    analysis_start: date,
    analysis_end: date,
    pattern_timeframe: PatternTimeframe = PatternTimeframe.DAILY,
    selected_horizon: int = 20,
    horizons: tuple[int, ...] = (2, 3, 5, 10, 20, 40, 60),
    bootstrap_resamples: int = 2_000,
    random_iterations: int = 1_000,
    random_seed: int = 20260817,
    cost_scenarios_bps: tuple[int, ...] = (0, 5, 10, 25, 50, 100),
) -> ReadableEdgeReport:
    """Reproduce the existing report, then add readable preliminary edge diagnostics."""

    if bootstrap_resamples < 100:
        raise ValueError("bootstrap_resamples must be at least 100")
    if random_iterations < 100:
        raise ValueError("random_iterations must be at least 100")
    if (
        not cost_scenarios_bps
        or any(value < 0 for value in cost_scenarios_bps)
        or len(set(cost_scenarios_bps)) != len(cost_scenarios_bps)
    ):
        raise ValueError("cost_scenarios_bps must contain unique non-negative values")

    normalized = _normalize_series(series_by_symbol)
    source = build_timeframe_universe_research_report(
        normalized,
        universe_id=universe_id,
        universe_label=universe_label,
        config=config,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        pattern_timeframe=pattern_timeframe,
        selected_horizon=selected_horizon,
        horizons=horizons,
    )
    strategy, baseline, random_candidates = _observation_sets(
        normalized,
        config=config,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        pattern_timeframe=pattern_timeframe,
        selected_horizon=selected_horizon,
    )
    _verify_source_report(source, strategy, baseline)

    performance = _performance(
        strategy,
        resamples=bootstrap_resamples,
        seed=random_seed,
    )
    simple = BaselineComparison(
        comparator_id="simple-trend-context-baseline-v0.1",
        comparator_description=source.comparator_definition,
        sample_size=len(baseline),
        mean_return=fmean(item.forward_return for item in baseline) if baseline else None,
        excess_mean_return=source.excess_mean_return,
        excess_interval=_paired_month_difference_interval(
            strategy,
            baseline,
            resamples=bootstrap_resamples,
            seed=random_seed + 1,
        ),
    )
    randomized = _random_timing_control(
        strategy,
        random_candidates,
        iterations=random_iterations,
        seed=random_seed + 2,
    )
    parameters = _parameter_readout(source)
    costs = tuple(
        CostSensitivityPoint(value, performance.mean_return - value / 10_000.0)
        for value in cost_scenarios_bps
    )
    break_even = performance.mean_return * 10_000.0 if performance.mean_return > 0 else None
    return ReadableEdgeReport(
        source_report=source,
        performance=performance,
        simple_baseline=simple,
        randomized_timing=randomized,
        parameter_robustness=parameters,
        cost_sensitivity=costs,
        break_even_round_trip_bps=break_even,
        verdict=_verdict(performance, simple, randomized, parameters),
    )


def _observation_sets(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    config: ConsolidationBreakoutConfig,
    analysis_start: date,
    analysis_end: date,
    pattern_timeframe: PatternTimeframe,
    selected_horizon: int,
) -> tuple[
    tuple[ReturnObservation, ...],
    tuple[ReturnObservation, ...],
    dict[str, tuple[ReturnObservation, ...]],
]:
    frames = (
        build_pattern_frames(series_by_symbol, pattern_timeframe)
        if pattern_timeframe is not PatternTimeframe.DAILY
        else {}
    )
    strategy: list[ReturnObservation] = []
    baseline: list[ReturnObservation] = []
    random_candidates: dict[str, tuple[ReturnObservation, ...]] = {}

    for symbol, bars in series_by_symbol.items():
        frame = frames.get(symbol)
        events = _events(
            bars,
            frame=frame,
            config=config,
            start=analysis_start,
            end=analysis_end,
        )
        event_by_id = {event.event_id: event for event in events}
        for outcome in measure_forward_outcomes(bars, events, horizons=(selected_horizon,)):
            if date.fromisoformat(outcome.exit_date) <= analysis_end:
                event = event_by_id[outcome.event_id]
                strategy.append(
                    ReturnObservation(symbol, event.signal_date, outcome.forward_return)
                )

        candidates = _eligible_signals(bars, frame=frame, config=config)
        random_candidates[symbol] = tuple(
            observation
            for candidate in candidates
            if (
                observation := _control_observation(
                    symbol,
                    bars,
                    candidate.daily_signal_index,
                    start=analysis_start,
                    end=analysis_end,
                    horizon=selected_horizon,
                )
            )
            is not None
        )
        baseline.extend(
            _baseline_observations(
                symbol,
                bars,
                candidates,
                start=analysis_start,
                end=analysis_end,
                horizon=selected_horizon,
                stride=5,
            )
        )

    strategy.sort(key=lambda item: (item.signal_date, item.symbol))
    baseline.sort(key=lambda item: (item.signal_date, item.symbol))
    return tuple(strategy), tuple(baseline), random_candidates


def _events(
    bars: tuple[ResearchBar, ...],
    *,
    frame: PatternSeriesFrame | None,
    config: ConsolidationBreakoutConfig,
    start: date,
    end: date,
) -> tuple[ConsolidationBreakoutEvent, ...]:
    if frame is None:
        detected = detect_consolidation_breakouts(bars, config)
    elif frame.bars:
        detected = remap_breakout_events_to_daily(
            detect_consolidation_breakouts(frame.bars, config),
            frame,
        )
    else:
        return ()
    return tuple(event for event in detected if start <= event.signal_date <= end)


def _eligible_signals(
    bars: tuple[ResearchBar, ...],
    *,
    frame: PatternSeriesFrame | None,
    config: ConsolidationBreakoutConfig,
) -> tuple[_EligibleSignal, ...]:
    if frame is None:
        return tuple(
            _EligibleSignal(index, index)
            for index in trend_qualified_indices(bars, config.trend_filter)
        )
    if not frame.bars:
        return ()
    return tuple(
        _EligibleSignal(
            pattern_index,
            source_index_for_pattern_index(frame, pattern_index),
        )
        for pattern_index in trend_qualified_indices(frame.bars, config.trend_filter)
    )


def _control_observation(
    symbol: str,
    bars: tuple[ResearchBar, ...],
    signal_index: int,
    *,
    start: date,
    end: date,
    horizon: int,
) -> ReturnObservation | None:
    signal = bars[signal_index]
    entry_index = signal_index + 1
    exit_index = entry_index + horizon - 1
    if (
        signal.trade_date < start
        or signal.trade_date > end
        or exit_index >= len(bars)
        or bars[exit_index].trade_date > end
    ):
        return None
    path = bars[entry_index : exit_index + 1]
    if not _usable(signal) or any(not _usable(item) for item in path):
        return None
    entry = bars[entry_index].open
    if entry <= 0:
        return None
    return ReturnObservation(symbol, signal.trade_date, path[-1].close / entry - 1.0)


def _baseline_observations(
    symbol: str,
    bars: tuple[ResearchBar, ...],
    candidates: tuple[_EligibleSignal, ...],
    *,
    start: date,
    end: date,
    horizon: int,
    stride: int,
) -> tuple[ReturnObservation, ...]:
    selected: list[ReturnObservation] = []
    last = -10_000
    for candidate in candidates:
        signal = bars[candidate.daily_signal_index]
        if signal.trade_date < start or signal.trade_date > end:
            continue
        if candidate.stride_index - last < stride:
            continue
        observation = _control_observation(
            symbol,
            bars,
            candidate.daily_signal_index,
            start=start,
            end=end,
            horizon=horizon,
        )
        if observation is not None:
            selected.append(observation)
            last = candidate.stride_index
    return tuple(selected)


def _verify_source_report(
    source: UniverseResearchReport,
    strategy: tuple[ReturnObservation, ...],
    baseline: tuple[ReturnObservation, ...],
) -> None:
    selected = source.selected_horizon_summary
    if selected.sample_size != len(strategy):
        raise RuntimeError("readable-edge strategy sample does not reproduce the source report")
    if source.baseline_sample_size != len(baseline):
        raise RuntimeError("readable-edge baseline sample does not reproduce the source report")
    if strategy and selected.mean_return is not None:
        if abs(fmean(item.forward_return for item in strategy) - selected.mean_return) > 1e-12:
            raise RuntimeError("readable-edge strategy mean does not reproduce the source report")
    if baseline and source.baseline_mean_return is not None:
        if (
            abs(fmean(item.forward_return for item in baseline) - source.baseline_mean_return)
            > 1e-12
        ):
            raise RuntimeError("readable-edge baseline mean does not reproduce the source report")


def _performance(
    observations: tuple[ReturnObservation, ...],
    *,
    resamples: int,
    seed: int,
) -> PerformanceReadout:
    if not observations:
        raise ValueError("readable edge requires at least one complete outcome")
    values = tuple(item.forward_return for item in observations)
    ordered = tuple(sorted(values))
    wins = tuple(value for value in values if value > 0)
    losses = tuple(value for value in values if value < 0)
    n = len(values)
    mean_value = fmean(values)
    win_rate = len(wins) / n
    avg_win = fmean(wins) if wins else None
    avg_loss = abs(fmean(losses)) if losses else None
    payoff = avg_win / avg_loss if avg_win is not None and avg_loss else None
    expectancy = win_rate * (avg_win or 0.0) - (len(losses) / n) * (avg_loss or 0.0)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    variance = fmean((value - mean_value) ** 2 for value in values)
    skewness = (
        fmean((value - mean_value) ** 3 for value in values) / variance**1.5
        if variance > 0 and n >= 3
        else None
    )
    kurtosis = (
        fmean((value - mean_value) ** 4 for value in values) / variance**2 - 3.0
        if variance > 0 and n >= 4
        else None
    )
    return PerformanceReadout(
        sample_size=n,
        mean_return=mean_value,
        median_return=median(values),
        standard_deviation=stdev(values) if n >= 2 else None,
        win_rate=win_rate,
        average_win=avg_win,
        average_loss=avg_loss,
        payoff_ratio=payoff,
        expectancy=expectancy,
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else None,
        minimum_return=ordered[0],
        p05_return=_quantile(ordered, 0.05),
        p25_return=_quantile(ordered, 0.25),
        p75_return=_quantile(ordered, 0.75),
        p95_return=_quantile(ordered, 0.95),
        maximum_return=ordered[-1],
        skewness=skewness,
        excess_kurtosis=kurtosis,
        top_five_profit_share=(
            sum(sorted(wins, reverse=True)[:5]) / gross_profit if gross_profit > 0 else None
        ),
        mean_interval=_clustered_mean_interval(observations, resamples=resamples, seed=seed),
        win_rate_interval=_wilson_interval(len(wins), n),
    )


def _random_timing_control(
    strategy: tuple[ReturnObservation, ...],
    candidates_by_symbol: Mapping[str, tuple[ReturnObservation, ...]],
    *,
    iterations: int,
    seed: int,
) -> RandomTimingControl:
    counts: dict[str, int] = defaultdict(int)
    for observation in strategy:
        counts[observation.symbol] += 1
    for symbol, count in counts.items():
        if len(candidates_by_symbol.get(symbol, ())) < count:
            raise ValueError(f"insufficient random-control candidates for {symbol}")

    rng = Random(seed)
    null_means: list[float] = []
    for _ in range(iterations):
        values: list[float] = []
        for symbol in sorted(counts):
            values.extend(
                item.forward_return
                for item in rng.sample(candidates_by_symbol[symbol], counts[symbol])
            )
        null_means.append(fmean(values))

    ordered = tuple(sorted(null_means))
    observed = fmean(item.forward_return for item in strategy)
    null_mean = fmean(ordered)
    return RandomTimingControl(
        comparator_id="same-instrument-random-trend-date-v0.1",
        comparator_description=(
            "Random trend-qualified eligible dates sampled without replacement within each "
            "instrument to match its complete event count and the selected holding horizon."
        ),
        iterations=iterations,
        random_seed=seed,
        eligible_candidate_count=sum(len(items) for items in candidates_by_symbol.values()),
        matched_event_count=len(strategy),
        null_mean_return=null_mean,
        null_p025=_quantile(ordered, 0.025),
        null_p975=_quantile(ordered, 0.975),
        excess_vs_null_mean=observed - null_mean,
        one_sided_p_value=(sum(value >= observed for value in ordered) + 1) / (iterations + 1),
    )


def _parameter_readout(source: UniverseResearchReport) -> ParameterRobustnessReadout:
    cells = source.parameter_surface
    positive = tuple(
        cell
        for cell in cells
        if cell.excess_mean_return is not None and cell.excess_mean_return > 0
    )
    durations = tuple(sorted({cell.duration for cell in cells}))
    tightness = tuple(sorted({cell.max_range_pct for cell in cells}))
    selected = next(
        (
            cell
            for cell in cells
            if cell.duration == source.selected_config.duration
            and abs(cell.max_range_pct - source.selected_config.max_range_pct) < 1e-12
        ),
        None,
    )
    neighbors = ()
    if selected is not None:
        di = durations.index(selected.duration)
        ti = tightness.index(selected.max_range_pct)
        neighbors = tuple(
            cell
            for cell in cells
            if cell != selected
            and abs(durations.index(cell.duration) - di) <= 1
            and abs(tightness.index(cell.max_range_pct) - ti) <= 1
        )
    neighbor_fraction = (
        sum(
            cell.excess_mean_return is not None and cell.excess_mean_return > 0
            for cell in neighbors
        )
        / len(neighbors)
        if neighbors
        else None
    )
    comparable = tuple(cell for cell in cells if cell.excess_mean_return is not None)
    best = (
        max(comparable, key=lambda cell: cast(float, cell.excess_mean_return))
        if comparable
        else None
    )
    return ParameterRobustnessReadout(
        searched_cell_count=len(cells),
        positive_excess_cell_count=len(positive),
        positive_excess_cell_fraction=len(positive) / len(cells) if cells else 0.0,
        selected_cell_excess=selected.excess_mean_return if selected else None,
        selected_neighbor_count=len(neighbors),
        selected_positive_neighbor_fraction=neighbor_fraction,
        best_cell_duration=best.duration if best else None,
        best_cell_max_range_pct=best.max_range_pct if best else None,
        best_cell_excess=best.excess_mean_return if best else None,
    )


def _verdict(
    performance: PerformanceReadout,
    baseline: BaselineComparison,
    randomized: RandomTimingControl,
    parameters: ParameterRobustnessReadout,
) -> EdgeVerdict:
    if performance.sample_size < 30:
        return EdgeVerdict(
            "INSUFFICIENT_SAMPLE",
            "Not enough complete outcomes to read a market-wide edge.",
            "The selected horizon has fewer than 30 complete event outcomes.",
        )
    if baseline.excess_mean_return is not None and baseline.excess_mean_return <= 0:
        return EdgeVerdict(
            "NO_EDGE_VS_SIMPLE_BASELINE",
            "No positive edge versus the current trend-context baseline.",
            (
                "Raw event returns can still be positive, but the strategy mean is not above "
                "the existing same-instrument trend-context baseline. That baseline is descriptive, "
                "so this is adverse evidence rather than a final rejection."
            ),
        )
    if randomized.excess_vs_null_mean <= 0 or randomized.one_sided_p_value >= 0.05:
        return EdgeVerdict(
            "NOT_DISTINGUISHABLE_FROM_RANDOM_TIMING",
            "The setup is not yet distinguishable from randomized eligible timing.",
            (
                "The preliminary same-instrument random-timing test does not show a positive "
                "incremental timing effect at the 5% one-sided level."
            ),
        )
    if performance.mean_interval is None or performance.mean_interval.lower <= 0:
        return EdgeVerdict(
            "RAW_EDGE_UNCERTAIN",
            "Positive point estimate, but the month-clustered mean interval crosses zero.",
            "Dependence-aware uncertainty does not yet support a stable positive raw effect.",
        )
    if (
        parameters.selected_positive_neighbor_fraction is not None
        and parameters.selected_positive_neighbor_fraction < 0.5
    ):
        return EdgeVerdict(
            "PARAMETER_REGION_UNSTABLE",
            "The preliminary effect is concentrated in an unstable parameter neighbourhood.",
            "Fewer than half of the adjacent duration/tightness cells show positive excess.",
        )
    return EdgeVerdict(
        "PRELIMINARY_EDGE",
        "Preliminary edge detected; validation is still incomplete.",
        (
            "The selected configuration clears the current baseline, randomized timing, raw "
            "mean-interval and local parameter-neighbourhood checks. Multiple-testing correction, "
            "OOS validation, full execution costs and portfolio simulation are still required."
        ),
    )


def _clustered_mean_interval(
    observations: tuple[ReturnObservation, ...],
    *,
    resamples: int,
    seed: int,
) -> ConfidenceInterval | None:
    clusters = _by_month(observations)
    keys = tuple(sorted(clusters))
    if len(keys) < 2:
        return None
    rng = Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled = tuple(rng.choice(keys) for _ in keys)
        estimates.append(fmean(value for key in sampled for value in clusters[key]))
    ordered = tuple(sorted(estimates))
    return ConfidenceInterval(
        _quantile(ordered, 0.025),
        _quantile(ordered, 0.975),
        0.95,
        "calendar-month cluster bootstrap",
        len(keys),
    )


def _paired_month_difference_interval(
    strategy: tuple[ReturnObservation, ...],
    baseline: tuple[ReturnObservation, ...],
    *,
    resamples: int,
    seed: int,
) -> ConfidenceInterval | None:
    left = _by_month(strategy)
    right = _by_month(baseline)
    keys = tuple(sorted(set(left) & set(right)))
    if len(keys) < 2:
        return None
    rng = Random(seed)
    estimates = []
    for _ in range(resamples):
        sampled = tuple(rng.choice(keys) for _ in keys)
        estimates.append(
            fmean(value for key in sampled for value in left[key])
            - fmean(value for key in sampled for value in right[key])
        )
    ordered = tuple(sorted(estimates))
    return ConfidenceInterval(
        _quantile(ordered, 0.025),
        _quantile(ordered, 0.975),
        0.95,
        "paired calendar-month cluster bootstrap",
        len(keys),
    )


def _wilson_interval(successes: int, n: int) -> ConfidenceInterval:
    p = successes / n
    denominator = 1.0 + _Z_95**2 / n
    center = (p + _Z_95**2 / (2.0 * n)) / denominator
    half = _Z_95 * sqrt(p * (1.0 - p) / n + _Z_95**2 / (4.0 * n**2)) / denominator
    return ConfidenceInterval(
        max(0.0, center - half),
        min(1.0, center + half),
        0.95,
        "Wilson score interval",
        n,
    )


def _by_month(
    observations: tuple[ReturnObservation, ...],
) -> dict[str, tuple[float, ...]]:
    values: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        values[observation.signal_date.strftime("%Y-%m")].append(observation.forward_return)
    return {key: tuple(items) for key, items in values.items()}


def _quantile(values: tuple[float, ...], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    position = probability * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _normalize_series(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
) -> dict[str, tuple[ResearchBar, ...]]:
    if not series_by_symbol:
        raise ValueError("readable edge requires at least one instrument series")
    normalized: dict[str, tuple[ResearchBar, ...]] = {}
    versions: set[str] = set()
    for raw_symbol, bars in series_by_symbol.items():
        symbol = raw_symbol.strip().upper()
        if not symbol or symbol in normalized or not bars:
            raise ValueError("symbols must be unique non-empty values with data")
        versions.update(str(bar.dataset_version) for bar in bars)
        normalized[symbol] = bars
    if len(versions) != 1:
        raise ValueError("readable edge cannot mix dataset versions")
    return dict(sorted(normalized.items()))


__all__ = [
    "BaselineComparison",
    "ConfidenceInterval",
    "CostSensitivityPoint",
    "EdgeVerdict",
    "ParameterRobustnessReadout",
    "PerformanceReadout",
    "RandomTimingControl",
    "ReadableEdgeReport",
    "ReturnObservation",
    "build_readable_edge_report",
]
