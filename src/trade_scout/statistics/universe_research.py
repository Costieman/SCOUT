"""Exploratory market-wide strategy research across a provider-neutral universe.

The analyzer applies one explicit strategy definition independently to each instrument, then
aggregates event frequency, breadth, outcome distributions, comparator returns, and a nearby
parameter surface. It does not optimize, validate, rank live candidates, or place trades.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from statistics import median

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.outcomes.forward_returns import (
    ForwardOutcome,
    HorizonSummary,
    measure_forward_outcomes,
    summarize_outcomes,
)
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    ConsolidationBreakoutEvent,
    TrendFilter,
    detect_consolidation_breakouts,
    trend_qualified_indices,
)


@dataclass(frozen=True, slots=True)
class MonthlyHitCount:
    """Opportunity availability for one calendar month in the analysis window."""

    month: str
    event_count: int
    instrument_count: int


@dataclass(frozen=True, slots=True)
class InstrumentResearchSummary:
    """Selected-horizon contribution from one instrument."""

    symbol: str
    event_count: int
    complete_outcome_count: int
    mean_return: float | None
    median_return: float | None
    positive_fraction: float | None


@dataclass(frozen=True, slots=True)
class UniverseParameterCell:
    """One duration/tightness cell under fixed trend, volume and outcome settings."""

    duration: int
    max_range_pct: float
    event_count: int
    instrument_count: int
    complete_outcome_count: int
    mean_return: float | None
    positive_fraction: float | None
    baseline_mean_return: float | None
    excess_mean_return: float | None
    mean_events_per_month: float


@dataclass(frozen=True, slots=True)
class UniverseResearchReport:
    """Presentation-ready descriptive evidence for one market-wide strategy request."""

    universe_id: str
    universe_label: str
    dataset_version: str
    analysis_start: date
    analysis_end: date
    selected_horizon: int
    selected_config: ConsolidationBreakoutConfig
    universe_instrument_count: int
    instruments_with_events: int
    instrument_breadth_fraction: float
    event_count: int
    selected_horizon_summary: HorizonSummary
    horizon_summaries: tuple[HorizonSummary, ...]
    baseline_sample_size: int
    baseline_mean_return: float | None
    excess_mean_return: float | None
    mean_events_per_month: float
    median_events_per_month: float
    max_events_in_month: int
    active_month_fraction: float
    top_five_event_share: float | None
    monthly_hits: tuple[MonthlyHitCount, ...]
    instrument_summaries: tuple[InstrumentResearchSummary, ...]
    parameter_surface: tuple[UniverseParameterCell, ...]
    warnings: tuple[str, ...]
    research_state: str = "EXPLORATORY"
    strategy_id: str = "consolidation_breakout"
    strategy_version: str = "consolidation-breakout-research-v0.2"
    event_definition_version: str = "consolidation-close-breakout-v0.2"
    outcome_definition_version: str = "next-open-forward-path-v0.1"
    comparator_definition: str = "same-instrument trend-context dates sampled every 5 sessions"


def build_universe_research_report(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    universe_id: str,
    universe_label: str,
    config: ConsolidationBreakoutConfig,
    analysis_start: date,
    analysis_end: date,
    selected_horizon: int = 20,
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60),
    surface_durations: tuple[int, ...] = (10, 20, 30, 40, 60),
    surface_tightness: tuple[float, ...] = (0.06, 0.09, 0.12, 0.15, 0.18),
) -> UniverseResearchReport:
    """Apply one strategy across every supplied instrument and aggregate descriptive evidence."""

    normalized = _validate_series(series_by_symbol)
    if analysis_end < analysis_start:
        raise ValueError("analysis_end must be on or after analysis_start")
    if selected_horizon not in horizons:
        raise ValueError("selected_horizon must be included in horizons")
    if not surface_durations or not surface_tightness:
        raise ValueError("parameter surface axes must not be empty")

    events_by_symbol: dict[str, tuple[ConsolidationBreakoutEvent, ...]] = {}
    outcomes_by_symbol: dict[str, tuple[ForwardOutcome, ...]] = {}
    all_outcomes: list[ForwardOutcome] = []
    all_events: list[ConsolidationBreakoutEvent] = []
    baseline_values: list[float] = []

    for symbol, bars in normalized.items():
        events = _events_in_window(
            detect_consolidation_breakouts(bars, config),
            start=analysis_start,
            end=analysis_end,
        )
        outcomes = _complete_outcomes_in_window(
            measure_forward_outcomes(bars, events, horizons=horizons),
            end=analysis_end,
        )
        events_by_symbol[symbol] = events
        outcomes_by_symbol[symbol] = outcomes
        all_events.extend(events)
        all_outcomes.extend(outcomes)
        baseline_values.extend(
            _baseline_returns(
                bars,
                trend_filter=config.trend_filter,
                start=analysis_start,
                end=analysis_end,
                horizon=selected_horizon,
                stride=5,
            )
        )

    summaries = summarize_outcomes(tuple(all_outcomes), horizons)
    selected = next(item for item in summaries if item.horizon == selected_horizon)
    baseline_mean = sum(baseline_values) / len(baseline_values) if baseline_values else None
    excess = (
        selected.mean_return - baseline_mean
        if selected.mean_return is not None and baseline_mean is not None
        else None
    )

    monthly_hits = _monthly_hits(
        tuple(all_events),
        analysis_start=analysis_start,
        analysis_end=analysis_end,
    )
    monthly_counts = tuple(item.event_count for item in monthly_hits)
    instruments_with_events = sum(bool(items) for items in events_by_symbol.values())
    breadth = instruments_with_events / len(normalized)
    top_five_share = _top_event_share(events_by_symbol, event_total=len(all_events), count=5)
    instrument_summaries = _instrument_summaries(
        events_by_symbol,
        outcomes_by_symbol,
        selected_horizon=selected_horizon,
    )
    parameter_surface = _parameter_surface(
        normalized,
        base_config=config,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        selected_horizon=selected_horizon,
        durations=surface_durations,
        tightness=surface_tightness,
    )

    return UniverseResearchReport(
        universe_id=universe_id,
        universe_label=universe_label,
        dataset_version=str(next(iter(normalized.values()))[0].dataset_version),
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        selected_horizon=selected_horizon,
        selected_config=config,
        universe_instrument_count=len(normalized),
        instruments_with_events=instruments_with_events,
        instrument_breadth_fraction=breadth,
        event_count=len(all_events),
        selected_horizon_summary=selected,
        horizon_summaries=summaries,
        baseline_sample_size=len(baseline_values),
        baseline_mean_return=baseline_mean,
        excess_mean_return=excess,
        mean_events_per_month=(sum(monthly_counts) / len(monthly_counts)),
        median_events_per_month=median(monthly_counts),
        max_events_in_month=max(monthly_counts),
        active_month_fraction=sum(value > 0 for value in monthly_counts) / len(monthly_counts),
        top_five_event_share=top_five_share,
        monthly_hits=monthly_hits,
        instrument_summaries=instrument_summaries,
        parameter_surface=parameter_surface,
        warnings=_warnings(
            universe_instrument_count=len(normalized),
            selected=selected,
            breadth=breadth,
            top_five_share=top_five_share,
            parameter_surface=parameter_surface,
        ),
    )


def _parameter_surface(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    base_config: ConsolidationBreakoutConfig,
    analysis_start: date,
    analysis_end: date,
    selected_horizon: int,
    durations: tuple[int, ...],
    tightness: tuple[float, ...],
) -> tuple[UniverseParameterCell, ...]:
    months = _month_keys(analysis_start, analysis_end)
    baseline_values: list[float] = []
    for bars in series_by_symbol.values():
        baseline_values.extend(
            _baseline_returns(
                bars,
                trend_filter=base_config.trend_filter,
                start=analysis_start,
                end=analysis_end,
                horizon=selected_horizon,
                stride=5,
            )
        )
    baseline_mean = sum(baseline_values) / len(baseline_values) if baseline_values else None

    cells: list[UniverseParameterCell] = []
    for duration in durations:
        for threshold in tightness:
            config = ConsolidationBreakoutConfig(
                duration=duration,
                max_range_pct=threshold,
                trend_filter=base_config.trend_filter,
                cooldown_sessions=base_config.cooldown_sessions,
                min_breakout_volume_ratio=base_config.min_breakout_volume_ratio,
                volume_lookback_sessions=base_config.volume_lookback_sessions,
            )
            events: list[ConsolidationBreakoutEvent] = []
            outcomes: list[ForwardOutcome] = []
            contributing: set[str] = set()
            for symbol, bars in series_by_symbol.items():
                selected_events = _events_in_window(
                    detect_consolidation_breakouts(bars, config),
                    start=analysis_start,
                    end=analysis_end,
                )
                if selected_events:
                    contributing.add(symbol)
                events.extend(selected_events)
                outcomes.extend(
                    _complete_outcomes_in_window(
                        measure_forward_outcomes(
                            bars,
                            selected_events,
                            horizons=(selected_horizon,),
                        ),
                        end=analysis_end,
                    )
                )
            returns = tuple(item.forward_return for item in outcomes)
            mean_return = sum(returns) / len(returns) if returns else None
            cells.append(
                UniverseParameterCell(
                    duration=duration,
                    max_range_pct=threshold,
                    event_count=len(events),
                    instrument_count=len(contributing),
                    complete_outcome_count=len(returns),
                    mean_return=mean_return,
                    positive_fraction=(
                        sum(value > 0 for value in returns) / len(returns) if returns else None
                    ),
                    baseline_mean_return=baseline_mean,
                    excess_mean_return=(
                        mean_return - baseline_mean
                        if mean_return is not None and baseline_mean is not None
                        else None
                    ),
                    mean_events_per_month=len(events) / len(months),
                )
            )
    return tuple(cells)


def _instrument_summaries(
    events_by_symbol: Mapping[str, tuple[ConsolidationBreakoutEvent, ...]],
    outcomes_by_symbol: Mapping[str, tuple[ForwardOutcome, ...]],
    *,
    selected_horizon: int,
) -> tuple[InstrumentResearchSummary, ...]:
    summaries: list[InstrumentResearchSummary] = []
    for symbol in events_by_symbol:
        selected = tuple(
            item for item in outcomes_by_symbol[symbol] if item.horizon == selected_horizon
        )
        returns = tuple(item.forward_return for item in selected)
        summaries.append(
            InstrumentResearchSummary(
                symbol=symbol,
                event_count=len(events_by_symbol[symbol]),
                complete_outcome_count=len(returns),
                mean_return=sum(returns) / len(returns) if returns else None,
                median_return=median(returns) if returns else None,
                positive_fraction=(
                    sum(value > 0 for value in returns) / len(returns) if returns else None
                ),
            )
        )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (-item.event_count, item.symbol),
        )
    )


def _baseline_returns(
    bars: tuple[ResearchBar, ...],
    *,
    trend_filter: TrendFilter,
    start: date,
    end: date,
    horizon: int,
    stride: int,
) -> tuple[float, ...]:
    candidates = trend_qualified_indices(bars, trend_filter)
    selected: list[int] = []
    last = -10_000
    for index in candidates:
        signal = bars[index]
        if signal.trade_date < start or signal.trade_date > end:
            continue
        if index - last < stride:
            continue
        entry_index = index + 1
        exit_index = entry_index + horizon - 1
        if exit_index >= len(bars) or bars[exit_index].trade_date > end:
            continue
        path = bars[entry_index : exit_index + 1]
        if not _usable(signal) or any(not _usable(item) for item in path):
            continue
        selected.append(index)
        last = index

    return tuple(bars[index + horizon].close / bars[index + 1].open - 1.0 for index in selected)


def _monthly_hits(
    events: tuple[ConsolidationBreakoutEvent, ...],
    *,
    analysis_start: date,
    analysis_end: date,
) -> tuple[MonthlyHitCount, ...]:
    keys = _month_keys(analysis_start, analysis_end)
    counts = {key: 0 for key in keys}
    instruments: dict[str, set[str]] = {key: set() for key in keys}
    for event in events:
        key = event.signal_date.strftime("%Y-%m")
        counts[key] += 1
        instruments[key].add(str(event.instrument_id))
    return tuple(
        MonthlyHitCount(
            month=key,
            event_count=counts[key],
            instrument_count=len(instruments[key]),
        )
        for key in keys
    )


def _month_keys(start: date, end: date) -> tuple[str, ...]:
    year = start.year
    month = start.month
    keys: list[str] = []
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return tuple(keys)


def _events_in_window(
    events: tuple[ConsolidationBreakoutEvent, ...],
    *,
    start: date,
    end: date,
) -> tuple[ConsolidationBreakoutEvent, ...]:
    return tuple(item for item in events if start <= item.signal_date <= end)


def _complete_outcomes_in_window(
    outcomes: tuple[ForwardOutcome, ...],
    *,
    end: date,
) -> tuple[ForwardOutcome, ...]:
    return tuple(item for item in outcomes if date.fromisoformat(item.exit_date) <= end)


def _top_event_share(
    events_by_symbol: Mapping[str, tuple[ConsolidationBreakoutEvent, ...]],
    *,
    event_total: int,
    count: int,
) -> float | None:
    if event_total == 0:
        return None
    ordered = sorted((len(items) for items in events_by_symbol.values()), reverse=True)
    return sum(ordered[:count]) / event_total


def _validate_series(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
) -> dict[str, tuple[ResearchBar, ...]]:
    if not series_by_symbol:
        raise ValueError("universe research requires at least one instrument series")
    normalized: dict[str, tuple[ResearchBar, ...]] = {}
    versions: set[str] = set()
    for raw_symbol, bars in series_by_symbol.items():
        symbol = raw_symbol.strip().upper()
        if not symbol or symbol in normalized:
            raise ValueError("universe symbols must be unique non-empty values")
        if not bars:
            raise ValueError(f"universe series {symbol} is empty")
        if len({item.instrument_id for item in bars}) != 1:
            raise ValueError(f"universe series {symbol} contains multiple instruments")
        if any(item.quality_status is not QualityStatus.PASS for item in bars):
            raise ValueError(f"universe series {symbol} contains non-PASS research rows")
        dates = tuple(item.trade_date for item in bars)
        if dates != tuple(sorted(dates)) or len(dates) != len(set(dates)):
            raise ValueError(f"universe series {symbol} is not unique date-increasing")
        versions.update(str(item.dataset_version) for item in bars)
        normalized[symbol] = bars
    if len(versions) != 1:
        raise ValueError("universe research cannot mix canonical dataset versions")
    return dict(sorted(normalized.items()))


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _warnings(
    *,
    universe_instrument_count: int,
    selected: HorizonSummary,
    breadth: float,
    top_five_share: float | None,
    parameter_surface: tuple[UniverseParameterCell, ...],
) -> tuple[str, ...]:
    warnings = [
        "Exploratory market-wide evidence only; positive results are not validated trade signals.",
        "Parameter surfaces are hypothesis-generating and remain exposed to multiple-testing risk.",
        "The current comparator is descriptive, not a matched or statistically independent control.",
    ]
    if universe_instrument_count < 50:
        warnings.append(
            "The current canonical research scope contains fewer than 50 instruments; "
            "do not describe it as an S&P 500-wide result."
        )
    if selected.sample_size < 100:
        warnings.append(
            f"Selected horizon has only {selected.sample_size} complete outcomes across the universe."
        )
    if breadth < 0.25:
        warnings.append(
            "Fewer than 25% of research-universe instruments contributed events; inspect concentration."
        )
    if top_five_share is not None and top_five_share > 0.35:
        warnings.append("The five most active instruments contribute more than 35% of events.")
    positive_cells = sum(
        item.excess_mean_return is not None and item.excess_mean_return > 0
        for item in parameter_surface
    )
    if positive_cells in {0, len(parameter_surface)}:
        warnings.append(
            "The nearby duration/tightness surface is one-sided; broader holdout testing is needed."
        )
    return tuple(warnings)


__all__ = [
    "InstrumentResearchSummary",
    "MonthlyHitCount",
    "UniverseParameterCell",
    "UniverseResearchReport",
    "build_universe_research_report",
]
