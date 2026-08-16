"""Deterministic synthetic market fixtures for research-engine verification."""

from trade_scout.synthetic.market_lab import (
    SyntheticAnnotation,
    SyntheticAnnotationKind,
    SyntheticMarketScenario,
    SyntheticScenarioKind,
    ambiguous_daily_bar_scenario,
    clean_trend_scenario,
    consolidation_breakout_scenario,
    false_breakout_scenario,
    gap_down_scenario,
    missing_bars_scenario,
    nested_bases_scenario,
    split_discontinuity_scenario,
    standard_market_laboratory,
    stop_out_scenario,
    volatility_shock_scenario,
)

__all__ = [
    "SyntheticAnnotation",
    "SyntheticAnnotationKind",
    "SyntheticMarketScenario",
    "SyntheticScenarioKind",
    "ambiguous_daily_bar_scenario",
    "clean_trend_scenario",
    "consolidation_breakout_scenario",
    "false_breakout_scenario",
    "gap_down_scenario",
    "missing_bars_scenario",
    "nested_bases_scenario",
    "split_discontinuity_scenario",
    "standard_market_laboratory",
    "stop_out_scenario",
    "volatility_shock_scenario",
]
