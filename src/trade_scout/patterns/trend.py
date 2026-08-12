"""Reusable point-in-time trend context for pattern research."""

from __future__ import annotations

from enum import StrEnum

from trade_scout.data.contracts import ResearchBar


class TrendFilter(StrEnum):
    """Point-in-time trend preconditions shared by pattern detectors."""

    NONE = "none"
    ABOVE_SMA_200 = "above_sma_200"
    ABOVE_RISING_SMA_200 = "above_rising_sma_200"
    ABOVE_SMA_50_100_200 = "above_sma_50_100_200"
    BULLISH_SMA_STACK_50_100_200 = "bullish_sma_stack_50_100_200"


def trend_qualified(
    bars: tuple[ResearchBar, ...],
    signal_index: int,
    trend_filter: TrendFilter,
) -> bool:
    """Evaluate one trend condition using only bars available through ``signal_index``."""

    if trend_filter is TrendFilter.NONE:
        return True
    if signal_index < 199:
        return False

    close = bars[signal_index].close
    sma_200 = _sma(bars, signal_index=signal_index, period=200)
    if close <= sma_200:
        return False
    if trend_filter is TrendFilter.ABOVE_SMA_200:
        return True
    if trend_filter in {
        TrendFilter.ABOVE_SMA_50_100_200,
        TrendFilter.BULLISH_SMA_STACK_50_100_200,
    }:
        sma_50 = _sma(bars, signal_index=signal_index, period=50)
        sma_100 = _sma(bars, signal_index=signal_index, period=100)
        if close <= sma_50 or close <= sma_100:
            return False
        if trend_filter is TrendFilter.ABOVE_SMA_50_100_200:
            return True
        return sma_50 > sma_100 > sma_200

    if signal_index < 219:
        return False
    sma_prior = _sma(bars, signal_index=signal_index - 20, period=200)
    return sma_200 > sma_prior


def trend_qualified_indices(
    bars: tuple[ResearchBar, ...],
    trend_filter: TrendFilter,
) -> tuple[int, ...]:
    """Return signal-date indices satisfying the selected point-in-time trend context."""

    start = required_trend_history_sessions(trend_filter) - 1
    return tuple(
        index
        for index in range(max(0, start), len(bars) - 1)
        if trend_qualified(bars, index, trend_filter)
    )


def required_trend_history_sessions(trend_filter: TrendFilter) -> int:
    """Return the minimum trailing sessions needed to evaluate one trend condition."""

    if trend_filter is TrendFilter.NONE:
        return 1
    if trend_filter is TrendFilter.ABOVE_RISING_SMA_200:
        return 220
    return 200


def _sma(bars: tuple[ResearchBar, ...], *, signal_index: int, period: int) -> float:
    if signal_index + 1 < period:
        raise ValueError("insufficient history for requested moving average")
    start = signal_index - period + 1
    return sum(item.close for item in bars[start : signal_index + 1]) / period


__all__ = [
    "TrendFilter",
    "required_trend_history_sessions",
    "trend_qualified",
    "trend_qualified_indices",
]
