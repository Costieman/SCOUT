"""Immutable strategy definitions built from safe market-feature expressions."""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.app.market_scanner_service import MarketScannerRequest, ScannerSortKey


@dataclass(frozen=True, slots=True)
class StrategyDefinition:
    """A named, reproducible market screen suitable for later backtest execution."""

    strategy_id: str
    name: str
    description: str
    expression: str
    sort_by: ScannerSortKey = "return_20"
    descending: bool = True
    limit: int = 100

    def __post_init__(self) -> None:
        if not self.strategy_id.strip():
            raise ValueError("strategy_id must be non-empty")
        if not self.name.strip():
            raise ValueError("strategy name must be non-empty")
        if not self.description.strip():
            raise ValueError("strategy description must be non-empty")
        if not self.expression.strip():
            raise ValueError("strategy expression must be non-empty")
        if not 1 <= self.limit <= 500:
            raise ValueError("strategy limit must be between 1 and 500")

    def scanner_request(self) -> MarketScannerRequest:
        """Materialize the strategy as a scanner request using the shared expression engine."""

        return MarketScannerRequest(
            expression=self.expression,
            sort_by=self.sort_by,
            descending=self.descending,
            limit=self.limit,
        )


MOMENTUM_RVOL_TREND = StrategyDefinition(
    strategy_id="momentum-rvol-trend-v0.1",
    name="Momentum + RVOL + Trend",
    description=(
        "Descriptive screen for positive 20-session momentum, elevated relative volume, "
        "and price above the trailing 200-session moving average."
    ),
    expression=(
        "return_20 >= 0.05 and relative_volume_20 >= 1.5 "
        "and distance_sma_200_pct > 0"
    ),
    sort_by="return_20",
    descending=True,
    limit=100,
)

LOW_VOL_TREND = StrategyDefinition(
    strategy_id="low-vol-trend-v0.1",
    name="Low Volatility Trend",
    description=(
        "Descriptive screen for positive annual momentum, below-threshold realized volatility, "
        "and price above the trailing 200-session moving average."
    ),
    expression=(
        "return_252 > 0 and realized_volatility_20 < 0.30 "
        "and distance_sma_200_pct > 0"
    ),
    sort_by="return_252",
    descending=True,
    limit=100,
)

STRATEGY_LIBRARY: tuple[StrategyDefinition, ...] = (
    MOMENTUM_RVOL_TREND,
    LOW_VOL_TREND,
)


__all__ = [
    "LOW_VOL_TREND",
    "MOMENTUM_RVOL_TREND",
    "STRATEGY_LIBRARY",
    "StrategyDefinition",
]
