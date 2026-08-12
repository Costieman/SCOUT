"""Historical descriptive research over immutable strategy definitions."""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.app.market_scanner_service import MarketScannerSource
from trade_scout.app.strategy_definition import StrategyDefinition
from trade_scout.app.strategy_outcome_service import (
    StrategyForwardOutcome,
    StrategyHorizonSummary,
    measure_strategy_forward_outcomes,
    summarize_strategy_outcomes,
)
from trade_scout.app.strategy_signal_history import StrategySignal, evaluate_strategy_signal_history
from trade_scout.data.contracts import DailyBar


@dataclass(frozen=True, slots=True)
class HistoricalStrategyResearchReport:
    """Point-in-time signals and descriptive forward outcomes for one named strategy."""

    strategy: StrategyDefinition
    horizons: tuple[int, ...]
    instrument_count: int
    signal_count: int
    signals: tuple[StrategySignal, ...]
    outcomes: tuple[StrategyForwardOutcome, ...]
    summaries: tuple[StrategyHorizonSummary, ...]


@dataclass(frozen=True, slots=True)
class HistoricalStrategyResearchService:
    source: MarketScannerSource

    def run(
        self,
        strategy: StrategyDefinition,
        *,
        horizons: tuple[int, ...] = (5, 20, 60),
    ) -> HistoricalStrategyResearchReport:
        series = self.source.canonical_series()
        bars = _flatten(series)
        signals = evaluate_strategy_signal_history(bars, strategy)
        outcomes = measure_strategy_forward_outcomes(bars, signals, horizons=horizons)
        summaries = summarize_strategy_outcomes(outcomes, horizons)
        return HistoricalStrategyResearchReport(
            strategy=strategy,
            horizons=horizons,
            instrument_count=len(series),
            signal_count=len(signals),
            signals=signals,
            outcomes=outcomes,
            summaries=summaries,
        )


def _flatten(series: dict[str, tuple[DailyBar, ...]]) -> tuple[DailyBar, ...]:
    return tuple(
        bar
        for symbol in sorted(series)
        for bar in sorted(series[symbol], key=lambda item: item.trade_date)
    )


__all__ = ["HistoricalStrategyResearchReport", "HistoricalStrategyResearchService"]
