"""Run immutable strategy definitions through the shared reviewed-market scanner."""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.app.market_scanner_service import (
    MarketScannerReport,
    MarketScannerService,
    MarketScannerSource,
)
from trade_scout.app.strategy_definition import StrategyDefinition


@dataclass(frozen=True, slots=True)
class StrategyRunReport:
    """One reproducible latest-state strategy evaluation."""

    strategy: StrategyDefinition
    scanner_report: MarketScannerReport

    @property
    def matched_symbol_count(self) -> int:
        return self.scanner_report.matched_symbol_count

    @property
    def scanned_symbol_count(self) -> int:
        return self.scanner_report.scanned_symbol_count


@dataclass(frozen=True, slots=True)
class StrategyRunnerService:
    """Execute a named strategy through the same feature/scanner semantics used by the app."""

    source: MarketScannerSource

    def run(self, strategy: StrategyDefinition) -> StrategyRunReport:
        report = MarketScannerService(self.source).run(strategy.scanner_request())
        return StrategyRunReport(strategy=strategy, scanner_report=report)


__all__ = ["StrategyRunReport", "StrategyRunnerService"]
