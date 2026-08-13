"""Multi-symbol exploratory consolidation-breakout research aggregation.

This module contains no provider or filesystem logic. It applies one frozen exploratory
configuration to a caller-supplied mapping of provider-independent ResearchBar series and
aggregates the existing single-symbol Edge Explorer reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Mapping

from trade_scout.data.contracts import ResearchBar
from trade_scout.outcomes.forward_returns import HorizonSummary
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig
from trade_scout.statistics.edge_explorer import EdgeExplorerReport, build_consolidation_edge_report


@dataclass(frozen=True, slots=True)
class BatchSymbolSummary:
    """Compact result for one symbol under one frozen batch definition."""

    symbol: str
    event_count: int
    selected_horizon: int
    selected_sample_size: int
    mean_return: float | None
    median_return: float | None
    positive_fraction: float | None
    baseline_sample_size: int
    baseline_mean_return: float | None
    excess_mean_return: float | None
    evidence_state: str
    current_state: str


@dataclass(frozen=True, slots=True)
class BatchHorizonSummary:
    """Cross-symbol summary built from symbol-level horizon estimates.

    The batch deliberately does not pool event-level observations here because doing so would
    silently treat clustered events as independent. Event-level pooled inference belongs in the
    later validation framework.
    """

    horizon: int
    contributing_symbol_count: int
    complete_event_count: int
    mean_of_symbol_means: float | None
    median_of_symbol_medians: float | None
    median_positive_fraction: float | None


@dataclass(frozen=True, slots=True)
class ConsolidationBatchReport:
    """Reproducible exploratory report for one frozen definition across many symbols."""

    dataset_version: str
    strategy_id: str
    strategy_version: str
    research_state: str
    selected_horizon: int
    selected_config: ConsolidationBreakoutConfig
    requested_symbol_count: int
    completed_symbol_count: int
    skipped_symbols: tuple[str, ...]
    total_event_count: int
    symbol_summaries: tuple[BatchSymbolSummary, ...]
    horizon_summaries: tuple[BatchHorizonSummary, ...]
    warnings: tuple[str, ...]
    batch_definition_version: str = "consolidation-batch-v0.1"


def build_consolidation_batch_report(
    series_by_symbol: Mapping[str, tuple[ResearchBar, ...]],
    *,
    config: ConsolidationBreakoutConfig,
    selected_horizon: int = 20,
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60),
) -> ConsolidationBatchReport:
    """Run the existing exploratory report across every supplied symbol.

    A symbol is skipped only when it lacks the minimum history required by the same single-symbol
    service rule. Analytical errors are not swallowed: they remain visible failures.
    """

    if not series_by_symbol:
        raise ValueError("series_by_symbol must not be empty")
    if selected_horizon not in horizons:
        raise ValueError("selected_horizon must be included in horizons")

    reports: list[EdgeExplorerReport] = []
    skipped: list[str] = []
    minimum_history = max(220, config.duration + selected_horizon + 1)

    for raw_symbol in sorted(series_by_symbol):
        symbol = raw_symbol.strip().upper()
        if not symbol:
            raise ValueError("batch symbols must be non-empty")
        bars = series_by_symbol[raw_symbol]
        if len(bars) < minimum_history:
            skipped.append(symbol)
            continue
        reports.append(
            build_consolidation_edge_report(
                bars,
                symbol=symbol,
                config=config,
                selected_horizon=selected_horizon,
                horizons=horizons,
            )
        )

    if not reports:
        raise ValueError("no symbol has sufficient history for the requested batch definition")

    dataset_versions = {item.dataset_version for item in reports}
    strategy_versions = {item.strategy_version for item in reports}
    research_states = {item.research_state for item in reports}
    if len(dataset_versions) != 1:
        raise ValueError("batch cannot mix canonical dataset versions")
    if len(strategy_versions) != 1 or len(research_states) != 1:
        raise ValueError("batch cannot mix strategy or research-state versions")

    symbol_summaries = tuple(_symbol_summary(item) for item in reports)
    horizon_summaries = tuple(
        _cross_symbol_horizon_summary(reports, horizon) for horizon in horizons
    )
    warnings = (
        "Exploratory multi-symbol evidence only; this report is not production validation.",
        "Cross-symbol summaries do not treat event observations as independent inference units.",
        "The underlying comparator remains the simple same-stock trend-context baseline.",
        (
            "Parameter optimization, multiplicity correction, holdout validation, costs, "
            "and stop research are outside this batch definition."
        ),
    )

    return ConsolidationBatchReport(
        dataset_version=next(iter(dataset_versions)),
        strategy_id="consolidation_breakout",
        strategy_version=next(iter(strategy_versions)),
        research_state=next(iter(research_states)),
        selected_horizon=selected_horizon,
        selected_config=config,
        requested_symbol_count=len(series_by_symbol),
        completed_symbol_count=len(reports),
        skipped_symbols=tuple(skipped),
        total_event_count=sum(item.event_count for item in reports),
        symbol_summaries=symbol_summaries,
        horizon_summaries=horizon_summaries,
        warnings=warnings,
    )


def _symbol_summary(report: EdgeExplorerReport) -> BatchSymbolSummary:
    selected = report.selected_horizon_summary
    return BatchSymbolSummary(
        symbol=report.symbol,
        event_count=report.event_count,
        selected_horizon=report.selected_horizon,
        selected_sample_size=selected.sample_size,
        mean_return=selected.mean_return,
        median_return=selected.median_return,
        positive_fraction=selected.positive_fraction,
        baseline_sample_size=report.baseline_sample_size,
        baseline_mean_return=report.baseline_mean_return,
        excess_mean_return=report.excess_mean_return,
        evidence_state=str(report.evidence_state),
        current_state=report.current_state.state,
    )


def _cross_symbol_horizon_summary(
    reports: list[EdgeExplorerReport],
    horizon: int,
) -> BatchHorizonSummary:
    selected: list[HorizonSummary] = []
    for report in reports:
        summary = next(item for item in report.horizon_summaries if item.horizon == horizon)
        if summary.sample_size > 0:
            selected.append(summary)

    means = [item.mean_return for item in selected if item.mean_return is not None]
    medians = [item.median_return for item in selected if item.median_return is not None]
    positive = [item.positive_fraction for item in selected if item.positive_fraction is not None]
    return BatchHorizonSummary(
        horizon=horizon,
        contributing_symbol_count=len(selected),
        complete_event_count=sum(item.sample_size for item in selected),
        mean_of_symbol_means=sum(means) / len(means) if means else None,
        median_of_symbol_medians=median(medians) if medians else None,
        median_positive_fraction=median(positive) if positive else None,
    )
