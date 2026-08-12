"""Point-in-time volume primitives shared by research and event engines."""

from __future__ import annotations

from trade_scout.data.contracts import ResearchBar


def relative_volume(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    lookback_sessions: int,
) -> float | None:
    """Return signal volume divided by the prior trailing mean volume.

    The signal bar is excluded from the baseline, so the value uses only information available
    before the signal session plus the signal session's observed volume itself.
    """

    if lookback_sessions < 2:
        raise ValueError("lookback_sessions must be at least 2")
    if signal_index < 0 or signal_index >= len(bars):
        raise IndexError("signal_index is outside the supplied bars")
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


__all__ = ["relative_volume"]
