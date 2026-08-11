"""Market-wide research where pattern timeframe is separate from daily holding horizon."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
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
from trade_scout.patterns.timeframes import (
    PatternSeriesFrame,
    PatternTimeframe,
    build_pattern_frames,
    remap_breakout_events_to_daily,
    source_index_for_pattern_index,
)
from trade_scout.statistics.universe_research import (
    InstrumentResearchSummary,
    MonthlyHitCount,
    UniverseParameterCell,
    UniverseResearchReport,
    build_universe_research_report,
)


def build_timeframe_universe_research_report(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    universe_id: str,
    universe_label: str,
    config: ConsolidationBreakoutConfig,
    analysis_start: date,
    analysis_end: date,
    pattern_timeframe: PatternTimeframe,
    selected_horizon: int = 20,
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60),
    surface_durations: tuple[int, ...] = (10, 20, 30, 40, 60),
    surface_tightness: tuple[float, ...] = (0.06, 0.09, 0.12, 0.15, 0.18),
) -> UniverseResearchReport:
    """Apply a pattern timeframe while keeping outcome horizons in daily trading sessions."""

    if pattern_timeframe is PatternTimeframe.DAILY:
        report = build_universe_research_report(
            series_by_symbol,
            universe_id=universe_id,
            universe_label=universe_label,
            config=config,
            analysis_start=analysis_start,
            analysis_end=analysis_end,
            selected_horizon=selected_horizon,
            horizons=horizons,
            surface_durations=surface_durations,
            surface_tightness=surface_tightness,
        )
        return replace(
            report,
            strategy_version="consolidation-breakout-research-v0.3:daily",
            comparator_definition=(
                "same-instrument daily trend-context bars sampled every 5 pattern bars; "
                "outcomes measured in daily trading sessions"
            ),
        )

    normalized = _validate_series(series_by_symbol)
    if analysis_end < analysis_start:
        raise ValueError("analysis_end must be on or after analysis_start")
    if selected_horizon not in horizons:
        raise ValueError("selected_horizon must be included in horizons")
    frames = build_pattern_frames(normalized, pattern_timeframe)
    if not any(frame.bars for frame in frames.values()):
        raise ValueError("selected pattern timeframe produced no complete pattern bars")

    events_by_symbol: dict[str, tuple[ConsolidationBreakoutEvent, ...]] = {}
    outcomes_by_symbol: dict[str, tuple[ForwardOutcome, ...]] = {}
    all_events: list[ConsolidationBreakoutEvent] = []
    all_outcomes: list[ForwardOutcome] = []
    baseline_values: list[float] = []

    for symbol, daily_bars in normalized.items():
        frame = frames[symbol]
        if not frame.bars:
            events_by_symbol[symbol] = ()
            outcomes_by_symbol[symbol] = ()
            continue
        pattern_events = detect_consolidation_breakouts(frame.bars, config)
        daily_events = _events_in_window(
            remap_breakout_events_to_daily(pattern_events, frame),
            start=analysis_start,
            end=analysis_end,
        )
        outcomes = _complete_outcomes_in_window(
            measure_forward_outcomes(daily_bars, daily_events, horizons=horizons),
            end=analysis_end,
        )
        events_by_symbol[symbol] = daily_events
        outcomes_by_symbol[symbol] = outcomes
        all_events.extend(daily_events)
        all_outcomes.extend(outcomes)
        baseline_values.extend(
            _timeframe_baseline_returns(
                daily_bars,
                frame,
                trend_filter=config.trend_filter,
                start=analysis_start,
                end=analysis_end,
                horizon=selected_horizon,
                stride=5,
            )
        )

    summaries = summarize_outcomes(tuple(all_outcomes), horizons)
    selected = next(item for item in summaries if item.horizon == selected_horizon)
    baseline_mean = _mean(tuple(baseline_values))
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
    top_five_share = _top_event_share(events_by_symbol, len(all_events), 5)
    parameter_surface = _parameter_surface(
        normalized,
        frames,
        base_config=config,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        selected_horizon=selected_horizon,
        durations=surface_durations,
        tightness=surface_tightness,
    )
    warnings = _warnings(
        pattern_timeframe=pattern_timeframe,
        anchor=next(frame.anchor_description for frame in frames.values()),
        universe_instrument_count=len(normalized),
        selected=selected,
        breadth=breadth,
        top_five_share=top_five_share,
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
        mean_events_per_month=sum(monthly_counts) / len(monthly_counts),
        median_events_per_month=median(monthly_counts),
        max_events_in_month=max(monthly_counts),
        active_month_fraction=sum(value > 0 for value in monthly_counts) / len(monthly_counts),
        top_five_event_share=top_five_share,
        monthly_hits=monthly_hits,
        instrument_summaries=_instrument_summaries(
            events_by_symbol,
            outcomes_by_symbol,
            selected_horizon=selected_horizon,
        ),
        parameter_surface=parameter_surface,
        warnings=warnings,
        strategy_version=f"consolidation-breakout-research-v0.3:{pattern_timeframe.value}",
        event_definition_version="consolidation-close-breakout-timeframe-v0.1",
        comparator_definition=(
            f"same-instrument {pattern_timeframe.value} trend-context bars sampled every 5 "
            "pattern bars; outcomes measured in daily trading sessions"
        ),
    )


def _parameter_surface(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    frames: Mapping[str, PatternSeriesFrame],
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
    for symbol, daily_bars in series_by_symbol.items():
        frame = frames[symbol]
        if frame.bars:
            baseline_values.extend(
                _timeframe_baseline_returns(
                    daily_bars,
                    frame,
                    trend_filter=base_config.trend_filter,
                    start=analysis_start,
                    end=analysis_end,
                    horizon=selected_horizon,
                    stride=5,
                )
            )
    baseline_mean = _mean(tuple(baseline_values))
    cells: list[UniverseParameterCell] = []
    for duration in durations:
        for threshold in tightness:
            config = replace(base_config, duration=duration, max_range_pct=threshold)
            events: list[ConsolidationBreakoutEvent] = []
            outcomes: list[ForwardOutcome] = []
            contributing: set[str] = set()
            for symbol, daily_bars in series_by_symbol.items():
                frame = frames[symbol]
                if not frame.bars:
                    continue
                detected = detect_consolidation_breakouts(frame.bars, config)
                daily_events = _events_in_window(
                    remap_breakout_events_to_daily(detected, frame),
                    start=analysis_start,
                    end=analysis_end,
                )
                if daily_events:
                    contributing.add(symbol)
                events.extend(daily_events)
                outcomes.extend(
                    _complete_outcomes_in_window(
                        measure_forward_outcomes(
                            daily_bars,
                            daily_events,
                            horizons=(selected_horizon,),
                        ),
                        end=analysis_end,
                    )
                )
            returns = tuple(item.forward_return for item in outcomes)
            mean_return = _mean(returns)
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


def _timeframe_baseline_returns(
    daily_bars: tuple[ResearchBar, ...],
    frame: PatternSeriesFrame,
    *,
    trend_filter: TrendFilter,
    start: date,
    end: date,
    horizon: int,
    stride: int,
) -> tuple[float, ...]:
    candidates = trend_qualified_indices(frame.bars, trend_filter)
    selected: list[int] = []
    last = -10_000
    for pattern_index in candidates:
        if pattern_index - last < stride:
            continue
        daily_signal_index = source_index_for_pattern_index(frame, pattern_index)
        signal = daily_bars[daily_signal_index]
        if signal.trade_date < start or signal.trade_date > end:
            continue
        entry_index = daily_signal_index + 1
        exit_index = entry_index + horizon - 1
        if exit_index >= len(daily_bars) or daily_bars[exit_index].trade_date > end:
            continue
        path = daily_bars[entry_index : exit_index + 1]
        if not _usable(signal) or any(not _usable(item) for item in path):
            continue
        selected.append(daily_signal_index)
        last = pattern_index
    return tuple(
        daily_bars[index + horizon].close / daily_bars[index + 1].open - 1.0
        for index in selected
    )


def _instrument_summaries(
    events_by_symbol: Mapping[str, tuple[ConsolidationBreakoutEvent, ...]],
    outcomes_by_symbol: Mapping[str, tuple[ForwardOutcome, ...]],
    *,
    selected_horizon: int,
) -> tuple[InstrumentResearchSummary, ...]:
    result: list[InstrumentResearchSummary] = []
    for symbol, events in events_by_symbol.items():
        outcomes = tuple(
            item for item in outcomes_by_symbol[symbol] if item.horizon == selected_horizon
        )
        returns = tuple(item.forward_return for item in outcomes)
        result.append(
            InstrumentResearchSummary(
                symbol=symbol,
                event_count=len(events),
                complete_outcome_count=len(returns),
                mean_return=_mean(returns),
                median_return=median(returns) if returns else None,
                positive_fraction=(
                    sum(value > 0 for value in returns) / len(returns) if returns else None
                ),
            )
        )
    return tuple(sorted(result, key=lambda item: (-item.event_count, item.symbol)))


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
        MonthlyHitCount(key, counts[key], len(instruments[key]))
        for key in keys
    )


def _month_keys(start: date, end: date) -> tuple[str, ...]:
    year, month = start.year, start.month
    keys: list[str] = []
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        if month == 12:
            year, month = year + 1, 1
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
        if not symbol or symbol in normalized or not bars:
            raise ValueError("universe symbols must be unique non-empty values with data")
        if len({item.instrument_id for item in bars}) != 1:
            raise ValueError(f"universe series {symbol} mixes instruments")
        dates = tuple(item.trade_date for item in bars)
        if tuple(sorted(dates)) != dates or len(set(dates)) != len(dates):
            raise ValueError(f"universe series {symbol} must be unique and date-increasing")
        versions.add(str(bars[0].dataset_version))
        normalized[symbol] = bars
    if len(versions) != 1:
        raise ValueError("universe research cannot mix canonical dataset versions")
    return dict(sorted(normalized.items()))


def _warnings(
    *,
    pattern_timeframe: PatternTimeframe,
    anchor: str,
    universe_instrument_count: int,
    selected: HorizonSummary,
    breadth: float,
    top_five_share: float | None,
) -> tuple[str, ...]:
    warnings = [
        "Pattern timeframe and holding horizon are separate: signals use aggregated pattern bars; "
        "entries and exits use daily bars.",
        f"Pattern-bar anchoring is fixed and reproducible: {anchor}.",
        "Multi-session timeframe results remain exploratory and require anchor/phase sensitivity tests.",
        "Parameter surfaces remain exposed to multiple-testing risk and are not validated strategies.",
    ]
    if pattern_timeframe is PatternTimeframe.WEEKLY:
        warnings.append(
            "The final calendar week is excluded unless the latest available market session is Friday."
        )
    if universe_instrument_count < 50:
        warnings.append("Research universe has fewer than 50 instruments; breadth evidence is limited.")
    if selected.sample_size < 100:
        warnings.append(
            f"Selected daily holding horizon has only {selected.sample_size} complete outcomes."
        )
    if breadth < 0.25:
        warnings.append("Fewer than 25% of instruments contributed events; inspect concentration.")
    if top_five_share is not None and top_five_share > 0.35:
        warnings.append("The five most active instruments contribute more than 35% of events.")
    return tuple(warnings)


def _usable(bar: ResearchBar) -> bool:
    return bar.eligibility and bar.quality_status is QualityStatus.PASS


def _mean(values: tuple[float, ...]) -> float | None:
    return sum(values) / len(values) if values else None


__all__ = ["build_timeframe_universe_research_report"]
