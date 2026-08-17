"""Predeclared exploratory templates for the feature-expression Strategy Builder.

Presets are convenience configurations, not endorsed strategies. They reuse the same point-in-time
feature engine, shared signal contract, exit policies, and validation boundaries as custom
expressions. Selecting a preset therefore changes configuration only; it does not create a new
backtest implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.statistics.strategy_research import StrategyDefinition, available_strategy_features


@dataclass(frozen=True, slots=True)
class StrategyPreset:
    """One named reusable feature-expression hypothesis template."""

    preset_id: str
    label: str
    description: str
    expression: str
    rank_feature: str
    descending: bool
    per_session_limit: int = 25
    version: str = "strategy-preset-v0.1"

    def __post_init__(self) -> None:
        if not self.preset_id.strip() or not self.label.strip() or not self.version.strip():
            raise ValueError("strategy preset identity, label, and version must be non-empty")
        if not self.expression.strip():
            raise ValueError("strategy preset expression must be non-empty")
        if self.rank_feature not in available_strategy_features():
            raise ValueError(f"unknown preset rank feature {self.rank_feature!r}")
        if not 1 <= self.per_session_limit <= 500:
            raise ValueError("strategy preset per-session limit must be between 1 and 500")

    def definition(self) -> StrategyDefinition:
        """Resolve the preset to the existing immutable strategy-definition contract."""

        return StrategyDefinition(
            strategy_id=f"preset:{self.preset_id}",
            name=self.label,
            expression=self.expression,
            rank_feature=self.rank_feature,
            descending=self.descending,
            per_session_limit=self.per_session_limit,
            description=self.description,
        )


_PRESETS = (
    StrategyPreset(
        preset_id="prior_high_20_breakout",
        label="20-session high breakout",
        description="Close above the prior 20-session high, ranked by breakout distance.",
        expression="distance_prior_high_20_pct > 0",
        rank_feature="distance_prior_high_20_pct",
        descending=True,
    ),
    StrategyPreset(
        preset_id="prior_high_55_breakout",
        label="55-session high breakout",
        description="Close above the prior 55-session high, ranked by breakout distance.",
        expression="distance_prior_high_55_pct > 0",
        rank_feature="distance_prior_high_55_pct",
        descending=True,
    ),
    StrategyPreset(
        preset_id="macd_bullish_cross_in_uptrend",
        label="MACD bullish cross in uptrend",
        description="MACD bullish crossover while price is above the 200-session moving average.",
        expression="macd_bullish_cross == 1 and distance_sma_200_pct > 0",
        rank_feature="return_20",
        descending=True,
    ),
    StrategyPreset(
        preset_id="sma_50_200_cross_up",
        label="SMA50 / SMA200 bullish cross",
        description="SMA50 crosses above SMA200, ranked by the resulting moving-average spread.",
        expression="sma_50_200_cross_up == 1",
        rank_feature="sma_50_200_spread_pct",
        descending=True,
    ),
    StrategyPreset(
        preset_id="rsi_pullback_rising_200",
        label="RSI pullback in rising long-term trend",
        description=(
            "RSI at or below 40 while price is above a rising SMA200; ranked from lowest RSI upward."
        ),
        expression=(
            "rsi_wilder_14 <= 40 and distance_sma_200_pct > 0 "
            "and sma_200_slope_20_pct > 0"
        ),
        rank_feature="rsi_wilder_14",
        descending=False,
    ),
    StrategyPreset(
        preset_id="momentum_volume_trend",
        label="20-session momentum + volume + trend",
        description=(
            "At least 5% 20-session return, relative volume at least 1.5x, and price above SMA200."
        ),
        expression=(
            "return_20 >= 0.05 and relative_volume_20 >= 1.5 "
            "and distance_sma_200_pct > 0"
        ),
        rank_feature="return_20",
        descending=True,
    ),
)


def available_strategy_presets() -> tuple[StrategyPreset, ...]:
    """Return the deterministic exploratory preset catalog."""

    return _PRESETS


def strategy_preset(preset_id: str) -> StrategyPreset:
    """Resolve a preset by stable ID or fail closed."""

    normalized = preset_id.strip()
    for preset in _PRESETS:
        if preset.preset_id == normalized:
            return preset
    raise ValueError(f"unknown strategy preset {preset_id!r}")


__all__ = ["StrategyPreset", "available_strategy_presets", "strategy_preset"]
