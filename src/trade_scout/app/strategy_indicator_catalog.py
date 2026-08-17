"""Presentation metadata for the Strategy Builder indicator/metric chooser.

This catalog describes currently executable point-in-time features. It is deliberately separate
from strategy presets: indicators are reusable building blocks and operators decide how to combine
them into a hypothesis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from trade_scout.statistics.strategy_research import available_strategy_features


@dataclass(frozen=True, slots=True)
class IndicatorMetricOption:
    """One executable metric exposed beneath an indicator family in the visual composer."""

    indicator_id: str
    indicator_label: str
    metric_id: str
    metric_label: str
    feature_name: str
    description: str
    unit_label: str
    default_operator: str
    default_value: float
    min_value: float
    max_value: float
    step: float
    parameter_summary: str


def _metric(
    indicator_id: str,
    indicator_label: str,
    feature_name: str,
    metric_label: str,
    description: str,
    unit_label: str,
    default_operator: str,
    default_value: float,
    min_value: float,
    max_value: float,
    step: float,
    parameter_summary: str,
) -> IndicatorMetricOption:
    return IndicatorMetricOption(
        indicator_id=indicator_id,
        indicator_label=indicator_label,
        metric_id=feature_name,
        metric_label=metric_label,
        feature_name=feature_name,
        description=description,
        unit_label=unit_label,
        default_operator=default_operator,
        default_value=default_value,
        min_value=min_value,
        max_value=max_value,
        step=step,
        parameter_summary=parameter_summary,
    )


_CATALOG = (
    _metric(
        "price_return",
        "Price return",
        "return_5",
        "5-session return",
        "Split-adjusted close return over five sessions.",
        "decimal",
        ">",
        0.0,
        -1.0,
        10.0,
        0.01,
        "5 sessions",
    ),
    _metric(
        "price_return",
        "Price return",
        "return_20",
        "20-session return",
        "Split-adjusted close return over twenty sessions.",
        "decimal",
        ">",
        0.05,
        -1.0,
        10.0,
        0.01,
        "20 sessions",
    ),
    _metric(
        "price_return",
        "Price return",
        "return_252",
        "252-session return",
        "Split-adjusted close return over 252 sessions.",
        "decimal",
        ">",
        0.0,
        -1.0,
        50.0,
        0.01,
        "252 sessions",
    ),
    _metric(
        "moving_average",
        "Moving average",
        "distance_sma_20_pct",
        "Price distance from SMA20",
        "Current close relative to SMA20.",
        "%",
        ">",
        0.0,
        -100.0,
        1000.0,
        0.1,
        "SMA 20",
    ),
    _metric(
        "moving_average",
        "Moving average",
        "distance_sma_50_pct",
        "Price distance from SMA50",
        "Current close relative to SMA50.",
        "%",
        ">",
        0.0,
        -100.0,
        1000.0,
        0.1,
        "SMA 50",
    ),
    _metric(
        "moving_average",
        "Moving average",
        "distance_sma_200_pct",
        "Price distance from SMA200",
        "Current close relative to SMA200.",
        "%",
        ">",
        0.0,
        -100.0,
        1000.0,
        0.1,
        "SMA 200",
    ),
    _metric(
        "moving_average",
        "Moving average",
        "sma_50_slope_20_pct",
        "SMA50 20-session slope",
        "Twenty-session percent change in SMA50.",
        "%",
        ">",
        0.0,
        -100.0,
        100.0,
        0.1,
        "SMA 50; slope 20 sessions",
    ),
    _metric(
        "moving_average",
        "Moving average",
        "sma_200_slope_20_pct",
        "SMA200 20-session slope",
        "Twenty-session percent change in SMA200.",
        "%",
        ">",
        0.0,
        -100.0,
        100.0,
        0.1,
        "SMA 200; slope 20 sessions",
    ),
    _metric(
        "moving_average",
        "Moving average",
        "sma_50_200_spread_pct",
        "SMA50 / SMA200 spread",
        "SMA50 relative to SMA200.",
        "%",
        ">",
        0.0,
        -100.0,
        1000.0,
        0.1,
        "SMA 50 vs SMA 200",
    ),
    _metric(
        "moving_average",
        "Moving average",
        "sma_50_200_cross_up",
        "SMA50 crosses above SMA200",
        "One on the session SMA50 crosses above SMA200.",
        "binary",
        "==",
        1.0,
        0.0,
        1.0,
        1.0,
        "SMA 50 / SMA 200 crossover",
    ),
    _metric(
        "macd",
        "MACD",
        "macd_line_pct",
        "MACD line",
        "EMA12 minus EMA26 as percent of close.",
        "%",
        ">",
        0.0,
        -100.0,
        100.0,
        0.01,
        "12 / 26 EMA",
    ),
    _metric(
        "macd",
        "MACD",
        "macd_signal_pct",
        "Signal line",
        "Nine-period EMA signal of MACD as percent of close.",
        "%",
        ">",
        0.0,
        -100.0,
        100.0,
        0.01,
        "12 / 26 / 9",
    ),
    _metric(
        "macd",
        "MACD",
        "macd_histogram_pct",
        "Histogram",
        "MACD line minus signal line as percent of close.",
        "%",
        ">",
        0.0,
        -100.0,
        100.0,
        0.01,
        "12 / 26 / 9",
    ),
    _metric(
        "macd",
        "MACD",
        "macd_bullish_cross",
        "Bullish signal crossover",
        "One when MACD crosses above its signal line.",
        "binary",
        "==",
        1.0,
        0.0,
        1.0,
        1.0,
        "12 / 26 / 9 crossover",
    ),
    _metric(
        "rsi",
        "RSI",
        "rsi_wilder_14",
        "Wilder RSI",
        "Wilder-smoothed RSI bounded from zero to one hundred.",
        "index",
        "<=",
        40.0,
        0.0,
        100.0,
        0.1,
        "14 sessions",
    ),
    _metric(
        "volume",
        "Volume",
        "relative_volume_20",
        "Relative volume",
        "Current volume divided by prior 20-session average volume.",
        "x",
        ">=",
        1.5,
        0.0,
        100.0,
        0.05,
        "20-session baseline",
    ),
    _metric(
        "volume",
        "Volume",
        "average_dollar_volume_20",
        "Average dollar volume",
        "Prior 20-session average raw close times raw volume.",
        "$",
        ">=",
        10_000_000.0,
        0.0,
        100_000_000_000.0,
        1_000_000.0,
        "20-session average",
    ),
    _metric(
        "volatility",
        "Volatility",
        "atr_pct_14",
        "ATR as % of price",
        "Fourteen-session ATR divided by close.",
        "%",
        "<=",
        5.0,
        0.0,
        100.0,
        0.1,
        "ATR 14",
    ),
    _metric(
        "volatility",
        "Volatility",
        "realized_volatility_20",
        "Realized volatility",
        "Annualized standard deviation of twenty one-session log returns.",
        "decimal",
        "<=",
        0.5,
        0.0,
        10.0,
        0.01,
        "20 sessions; annualized",
    ),
    _metric(
        "breakout",
        "Breakout / range",
        "distance_prior_high_20_pct",
        "Distance from prior 20-session high",
        "Close relative to the prior 20-session high; current session excluded from the range.",
        "%",
        ">",
        0.0,
        -100.0,
        1000.0,
        0.1,
        "Prior 20 sessions",
    ),
    _metric(
        "breakout",
        "Breakout / range",
        "distance_prior_high_55_pct",
        "Distance from prior 55-session high",
        "Close relative to the prior 55-session high; current session excluded from the range.",
        "%",
        ">",
        0.0,
        -100.0,
        1000.0,
        0.1,
        "Prior 55 sessions",
    ),
    _metric(
        "breakout",
        "Breakout / range",
        "range_position_prior_20",
        "Position in prior 20-session range",
        "Close position in the prior 20-session range; values may leave the zero-to-one interval.",
        "ratio",
        ">=",
        1.0,
        -10.0,
        10.0,
        0.01,
        "Prior 20 sessions",
    ),
)


def available_indicator_metrics() -> tuple[IndicatorMetricOption, ...]:
    """Return executable indicator metrics after checking feature-registry consistency."""

    available = set(available_strategy_features())
    missing = sorted({item.feature_name for item in _CATALOG} - available)
    if missing:
        raise RuntimeError(f"visual indicator catalog references unavailable features: {missing}")
    return _CATALOG


def indicator_catalog_json_ready() -> list[dict[str, object]]:
    """Return JSON-serializable catalog metadata for the local browser composer."""

    return [asdict(item) for item in available_indicator_metrics()]


__all__ = ["IndicatorMetricOption", "available_indicator_metrics", "indicator_catalog_json_ready"]
