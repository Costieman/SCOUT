"""Exploratory evidence summaries for the Trade Scout Edge Explorer.

These summaries help locate candidate regions for follow-up research. They deliberately do
not perform promotion, multiple-testing correction, holdout validation, or production ranking.
A positive cell is a hypothesis-generating observation, not proof of an edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from statistics import median

from trade_scout.data.contracts import ResearchBar
from trade_scout.outcomes.forward_returns import (
    HorizonSummary,
    measure_baseline_outcomes,
    measure_forward_outcomes,
    summarize_outcomes,
)
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    CurrentConsolidationState,
    TrendFilter,
    current_consolidation_state,
    detect_consolidation_breakouts,
    trend_qualified_indices,
)


class ExploratoryEvidenceState(StrEnum):
    """Non-promotional labels for one selected horizon."""

    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    EXPLORATORY_POSITIVE = "EXPLORATORY_POSITIVE"
    EXPLORATORY_NEGATIVE = "EXPLORATORY_NEGATIVE"
    MIXED = "MIXED"
    NO_EVENTS = "NO_EVENTS"


@dataclass(frozen=True, slots=True)
class ParameterSurfaceCell:
    duration: int
    max_range_pct: float
    event_count: int
    mean_return: float | None
    baseline_mean_return: float | None
    excess_mean_return: float | None
    median_return: float | None
    positive_fraction: float | None


@dataclass(frozen=True, slots=True)
class EdgeExplorerReport:
    """Presentation-ready analytical output for one stock/strategy request."""

    symbol: str
    strategy_id: str
    strategy_version: str
    dataset_version: str
    selected_horizon: int
    selected_config: ConsolidationBreakoutConfig
    event_count: int
    selected_horizon_summary: HorizonSummary
    baseline_sample_size: int
    baseline_mean_return: float | None
    excess_mean_return: float | None
    evidence_state: ExploratoryEvidenceState
    current_state: CurrentConsolidationState
    horizon_summaries: tuple[HorizonSummary, ...]
    parameter_surface: tuple[ParameterSurfaceCell, ...]
    recent_event_dates: tuple[str, ...]
    warnings: tuple[str, ...]
    research_state: str = "EXPLORATORY"
    comparator_definition: str = "same-stock trend-context dates sampled every 5 sessions"
    event_definition_version: str = "consolidation-close-breakout-v0.1"
    outcome_definition_version: str = "next-open-forward-path-v0.1"


def build_consolidation_edge_report(
    bars: tuple[ResearchBar, ...],
    *,
    symbol: str,
    config: ConsolidationBreakoutConfig,
    selected_horizon: int = 20,
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60),
    surface_durations: tuple[int, ...] = (10, 20, 30, 40, 60),
    surface_tightness: tuple[float, ...] = (0.06, 0.09, 0.12, 0.15, 0.18),
) -> EdgeExplorerReport:
    """Build one exploratory report and nearby-parameter surface."""

    if selected_horizon not in horizons:
        raise ValueError("selected_horizon must be included in horizons")
    events = detect_consolidation_breakouts(bars, config)
    outcomes = measure_forward_outcomes(bars, events, horizons=horizons)
    summaries = summarize_outcomes(outcomes, horizons)
    selected = next(item for item in summaries if item.horizon == selected_horizon)

    baseline_indices = trend_qualified_indices(bars, config.trend_filter)
    baseline = measure_baseline_outcomes(
        bars,
        baseline_indices,
        horizons=horizons,
        stride=5,
    )[selected_horizon]
    baseline_mean = sum(baseline) / len(baseline) if baseline else None
    excess = (
        selected.mean_return - baseline_mean
        if selected.mean_return is not None and baseline_mean is not None
        else None
    )

    surface = _parameter_surface(
        bars,
        trend_filter=config.trend_filter,
        selected_horizon=selected_horizon,
        durations=surface_durations,
        tightness=surface_tightness,
    )
    warnings = _warnings(
        selected=selected,
        baseline_size=len(baseline),
        surface=surface,
    )
    return EdgeExplorerReport(
        symbol=symbol.upper(),
        strategy_id="consolidation_breakout",
        strategy_version="consolidation-breakout-research-v0.1",
        dataset_version=str(bars[0].dataset_version),
        selected_horizon=selected_horizon,
        selected_config=config,
        event_count=len(events),
        selected_horizon_summary=selected,
        baseline_sample_size=len(baseline),
        baseline_mean_return=baseline_mean,
        excess_mean_return=excess,
        evidence_state=_evidence_state(selected, excess),
        current_state=current_consolidation_state(bars, config),
        horizon_summaries=summaries,
        parameter_surface=surface,
        recent_event_dates=tuple(item.signal_date.isoformat() for item in events[-10:]),
        warnings=warnings,
    )


def _parameter_surface(
    bars: tuple[ResearchBar, ...],
    *,
    trend_filter: TrendFilter,
    selected_horizon: int,
    durations: tuple[int, ...],
    tightness: tuple[float, ...],
) -> tuple[ParameterSurfaceCell, ...]:
    if not durations or not tightness:
        raise ValueError("parameter surface axes must not be empty")
    baseline_indices = trend_qualified_indices(bars, trend_filter)
    baseline_values = measure_baseline_outcomes(
        bars,
        baseline_indices,
        horizons=(selected_horizon,),
        stride=5,
    )[selected_horizon]
    baseline_mean = (
        sum(baseline_values) / len(baseline_values) if baseline_values else None
    )

    cells: list[ParameterSurfaceCell] = []
    for duration in durations:
        for threshold in tightness:
            config = ConsolidationBreakoutConfig(
                duration=duration,
                max_range_pct=threshold,
                trend_filter=trend_filter,
                cooldown_sessions=5,
            )
            events = detect_consolidation_breakouts(bars, config)
            outcomes = measure_forward_outcomes(
                bars,
                events,
                horizons=(selected_horizon,),
            )
            returns = tuple(item.forward_return for item in outcomes)
            mean_return = sum(returns) / len(returns) if returns else None
            cells.append(
                ParameterSurfaceCell(
                    duration=duration,
                    max_range_pct=threshold,
                    event_count=len(returns),
                    mean_return=mean_return,
                    baseline_mean_return=baseline_mean,
                    excess_mean_return=(
                        mean_return - baseline_mean
                        if mean_return is not None and baseline_mean is not None
                        else None
                    ),
                    median_return=median(returns) if returns else None,
                    positive_fraction=(
                        sum(value > 0 for value in returns) / len(returns) if returns else None
                    ),
                )
            )
    return tuple(cells)


def _evidence_state(
    summary: HorizonSummary,
    excess: float | None,
) -> ExploratoryEvidenceState:
    if summary.sample_size == 0:
        return ExploratoryEvidenceState.NO_EVENTS
    if summary.sample_size < 10:
        return ExploratoryEvidenceState.INSUFFICIENT_SAMPLE
    if excess is None:
        return ExploratoryEvidenceState.MIXED
    if excess > 0 and (summary.positive_fraction or 0) >= 0.5:
        return ExploratoryEvidenceState.EXPLORATORY_POSITIVE
    if excess < 0 and (summary.positive_fraction or 0) < 0.5:
        return ExploratoryEvidenceState.EXPLORATORY_NEGATIVE
    return ExploratoryEvidenceState.MIXED


def _warnings(
    *,
    selected: HorizonSummary,
    baseline_size: int,
    surface: tuple[ParameterSurfaceCell, ...],
) -> tuple[str, ...]:
    warnings = [
        "Exploratory single-stock evidence only; this is not a validated trade signal.",
        "The comparator is a simple same-stock trend-context baseline, not a matched or independent control.",
        "Parameter-surface highs are hypothesis-generating and are exposed to multiple-testing/data-mining risk.",
    ]
    if selected.sample_size < 10:
        warnings.append(
            f"Selected horizon has only {selected.sample_size} complete breakout outcomes; treat estimates as unstable."
        )
    if baseline_size < 20:
        warnings.append(
            f"Comparator has only {baseline_size} observations at the selected horizon."
        )
    positive_cells = sum(
        item.excess_mean_return is not None and item.excess_mean_return > 0 for item in surface
    )
    if positive_cells in {0, len(surface)}:
        warnings.append(
            "The nearby-parameter surface is one-sided; broader instruments/time periods are needed before interpretation."
        )
    return tuple(warnings)
