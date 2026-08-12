"""Shared point-in-time volume context for pattern/event research."""

from __future__ import annotations

from trade_scout.data.contracts import ResearchBar


def trailing_volume_ratio(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    lookback_sessions: int,
) -> float | None:
    """Return signal volume divided by the prior trailing-volume mean.

    The signal session is excluded from the baseline so the value is point-in-time equivalent to
    the exploratory consolidation-breakout detector's existing volume semantics.
    """

    if lookback_sessions < 2:
        raise ValueError("lookback_sessions must be at least 2")
    if not 0 <= signal_index < len(bars):
        raise ValueError("signal_index must identify an input bar")
    if signal_index < lookback_sessions:
        return None

    trailing = bars[signal_index - lookback_sessions : signal_index]
    signal = bars[signal_index]
    if any(item.volume < 0 for item in trailing) or signal.volume < 0:
        return None
    average = sum(item.volume for item in trailing) / lookback_sessions
    if average <= 0:
        return None
    return signal.volume / average
