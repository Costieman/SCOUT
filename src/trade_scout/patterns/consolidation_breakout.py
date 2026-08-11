"""Deterministic exploratory consolidation-breakout detection.

This module is analytical code, not UI logic. It implements a deliberately narrow first
research definition that can be exercised in the Edge Explorer while the wider Pattern &
Event Engine is still being built. Events use only information available on or before the
signal date and never inspect forward outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from trade_scout.data.contracts import InstrumentId, QualityStatus, ResearchBar


class TrendFilter(StrEnum):
    """Point-in-time trend preconditions supported by the exploratory detector."""

    NONE = "none"
    ABOVE_SMA_200 = "above_sma_200"
    ABOVE_RISING_SMA_200 = "above_rising_sma_200"


@dataclass(frozen=True, slots=True)
class ConsolidationBreakoutConfig:
    """Resolved Version 0.1 close-breakout configuration."""

    duration: int = 20
    max_range_pct: float = 0.12
    trend_filter: TrendFilter = TrendFilter.ABOVE_RISING_SMA_200
    cooldown_sessions: int = 5

    def __post_init__(self) -> None:
        if not 5 <= self.duration <= 252:
            raise ValueError("duration must be between 5 and 252 sessions")
        if not 0 < self.max_range_pct <= 1:
            raise ValueError("max_range_pct must be in (0, 1]")
        if not 0 <= self.cooldown_sessions <= 252:
            raise ValueError("cooldown_sessions must be between 0 and 252")


@dataclass(frozen=True, slots=True)
class ConsolidationBreakoutEvent:
    """One close-confirmed upside breakout from a qualified prior window."""

    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    formation_start: date
    formation_end: date
    boundary: float
    signal_close: float
    base_range_pct: float
    duration: int
    trend_filter: TrendFilter
    dataset_version: str
    event_definition_version: str = "consolidation-close-breakout-v0.1"


@dataclass(frozen=True, slots=True)
class CurrentConsolidationState:
    """Latest observable state for the same resolved definition."""

    state: str
    as_of_date: date
    boundary: float | None
    base_range_pct: float | None
    distance_to_boundary_pct: float | None
    trend_qualified: bool
    message: str


def detect_consolidation_breakouts(
    bars: tuple[ResearchBar, ...],
    config: ConsolidationBreakoutConfig,
) -> tuple[ConsolidationBreakoutEvent, ...]:
    """Detect close breakouts without looking beyond each signal bar."""

    _validate_bars(bars)
    if len(bars) <= config.duration:
        return ()

    events: list[ConsolidationBreakoutEvent] = []
    last_event_index = -10_000
    for signal_index in range(config.duration, len(bars)):
        if signal_index - last_event_index <= config.cooldown_sessions:
            continue
        event = _event_at(bars, signal_index=signal_index, config=config)
        if event is None:
            continue
        events.append(event)
        last_event_index = signal_index
    return tuple(events)


def current_consolidation_state(
    bars: tuple[ResearchBar, ...],
    config: ConsolidationBreakoutConfig,
) -> CurrentConsolidationState:
    """Classify the latest bar using only information available as of that bar."""

    _validate_bars(bars)
    latest = bars[-1]
    if len(bars) <= config.duration:
        return CurrentConsolidationState(
            state="INSUFFICIENT_HISTORY",
            as_of_date=latest.trade_date,
            boundary=None,
            base_range_pct=None,
            distance_to_boundary_pct=None,
            trend_qualified=False,
            message=f"Need at least {config.duration + 1} sessions for this definition.",
        )

    base = bars[-config.duration - 1 : -1]
    boundary = max(item.high for item in base)
    base_low = min(item.low for item in base)
    range_pct = _range_pct(boundary, base_low)
    trend_ok = _trend_qualified(bars, len(bars) - 1, config.trend_filter)
    distance = (boundary - latest.close) / boundary if boundary else None

    if range_pct > config.max_range_pct:
        state = "NOT_QUALIFIED"
        message = "Latest prior window is wider than the configured consolidation threshold."
    elif not trend_ok:
        state = "TREND_FILTER_FAIL"
        message = "Consolidation is tight enough, but the configured trend condition is not met."
    elif latest.close > boundary:
        state = "BREAKOUT"
        message = "Latest close is above the prior qualified consolidation boundary."
    else:
        state = "TRIGGER_READY"
        message = "A qualified consolidation exists; the latest close remains below its boundary."

    return CurrentConsolidationState(
        state=state,
        as_of_date=latest.trade_date,
        boundary=boundary,
        base_range_pct=range_pct,
        distance_to_boundary_pct=distance,
        trend_qualified=trend_ok,
        message=message,
    )


def trend_qualified_indices(
    bars: tuple[ResearchBar, ...],
    trend_filter: TrendFilter,
) -> tuple[int, ...]:
    """Return signal-date indices satisfying the same point-in-time trend context."""

    _validate_bars(bars)
    start = 0 if trend_filter is TrendFilter.NONE else 200
    return tuple(
        index
        for index in range(start, len(bars) - 1)
        if _trend_qualified(bars, index, trend_filter)
    )


def _event_at(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    config: ConsolidationBreakoutConfig,
) -> ConsolidationBreakoutEvent | None:
    signal = bars[signal_index]
    base = bars[signal_index - config.duration : signal_index]
    if any(not item.eligibility or item.quality_status is not QualityStatus.PASS for item in base):
        return None
    if not signal.eligibility or signal.quality_status is not QualityStatus.PASS:
        return None

    boundary = max(item.high for item in base)
    base_low = min(item.low for item in base)
    range_pct = _range_pct(boundary, base_low)
    if range_pct > config.max_range_pct:
        return None
    if not _trend_qualified(bars, signal_index, config.trend_filter):
        return None
    if signal.close <= boundary:
        return None

    return ConsolidationBreakoutEvent(
        event_id=(
            f"{signal.instrument_id}:consolidation-close-breakout-v0.1:"
            f"{signal.trade_date.isoformat()}:{config.duration}:{config.max_range_pct:.6f}:"
            f"{config.trend_filter.value}"
        ),
        instrument_id=signal.instrument_id,
        signal_date=signal.trade_date,
        signal_index=signal_index,
        formation_start=base[0].trade_date,
        formation_end=base[-1].trade_date,
        boundary=boundary,
        signal_close=signal.close,
        base_range_pct=range_pct,
        duration=config.duration,
        trend_filter=config.trend_filter,
        dataset_version=str(signal.dataset_version),
    )


def _trend_qualified(
    bars: tuple[ResearchBar, ...],
    signal_index: int,
    trend_filter: TrendFilter,
) -> bool:
    if trend_filter is TrendFilter.NONE:
        return True
    if signal_index < 199:
        return False
    sma_now = sum(item.close for item in bars[signal_index - 199 : signal_index + 1]) / 200
    if bars[signal_index].close <= sma_now:
        return False
    if trend_filter is TrendFilter.ABOVE_SMA_200:
        return True
    if signal_index < 219:
        return False
    sma_prior = sum(item.close for item in bars[signal_index - 219 : signal_index - 19]) / 200
    return sma_now > sma_prior


def _range_pct(high: float, low: float) -> float:
    if low <= 0:
        raise ValueError("research prices must be positive")
    return (high - low) / low


def _validate_bars(bars: tuple[ResearchBar, ...]) -> None:
    if not bars:
        raise ValueError("at least one research bar is required")
    instrument_ids = {item.instrument_id for item in bars}
    dataset_versions = {item.dataset_version for item in bars}
    if len(instrument_ids) != 1:
        raise ValueError("consolidation detection requires one instrument")
    if len(dataset_versions) != 1:
        raise ValueError("consolidation detection requires one dataset version")
    dates = [item.trade_date for item in bars]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise ValueError("research bars must be unique and date-increasing")
    if any(min(item.open, item.high, item.low, item.close) <= 0 for item in bars):
        raise ValueError("research prices must be positive")
