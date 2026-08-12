"""Batch consolidation-event generation through the PatternState boundary.

This module composes the pure consolidation pattern detector with the discrete event
layer. It owns event confirmation, optional volume confirmation, and cooldown-based
deduplication. Pattern geometry remains upstream and forward outcomes remain downstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from trade_scout.data.contracts import ResearchBar
from trade_scout.events.consolidation_breakout import (
    ConsolidationBreakoutEvent,
    event_from_pattern_state,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig
from trade_scout.patterns.consolidation_state import qualified_pattern_at


@dataclass(frozen=True, slots=True)
class ConsolidationEventConfig:
    """Event-side confirmation and deduplication settings."""

    cooldown_sessions: int = 5
    min_breakout_volume_ratio: float | None = None
    volume_lookback_sessions: int = 20

    def __post_init__(self) -> None:
        if not 0 <= self.cooldown_sessions <= 252:
            raise ValueError("cooldown_sessions must be between 0 and 252")
        if self.min_breakout_volume_ratio is not None and self.min_breakout_volume_ratio <= 0:
            raise ValueError("min_breakout_volume_ratio must be positive when supplied")
        if not 2 <= self.volume_lookback_sessions <= 252:
            raise ValueError("volume_lookback_sessions must be between 2 and 252")

    @classmethod
    def from_legacy_config(cls, config: ConsolidationBreakoutConfig) -> ConsolidationEventConfig:
        """Preserve current exploratory event semantics during migration."""

        return cls(
            cooldown_sessions=config.cooldown_sessions,
            min_breakout_volume_ratio=config.min_breakout_volume_ratio,
            volume_lookback_sessions=config.volume_lookback_sessions,
        )


def detect_consolidation_events(
    bars: tuple[ResearchBar, ...],
    pattern_config: ConsolidationBreakoutConfig,
    *,
    event_config: ConsolidationEventConfig | None = None,
) -> tuple[ConsolidationBreakoutEvent, ...]:
    """Generate deduplicated breakout events through canonical PatternState snapshots."""

    if not bars:
        raise ValueError("at least one research bar is required")
    resolved_event_config = event_config or ConsolidationEventConfig.from_legacy_config(
        pattern_config
    )
    events: list[ConsolidationBreakoutEvent] = []
    last_event_index = -10_000

    for signal_index in range(pattern_config.duration, len(bars)):
        if signal_index - last_event_index <= resolved_event_config.cooldown_sessions:
            continue
        pattern = qualified_pattern_at(
            bars,
            signal_index=signal_index,
            config=pattern_config,
        )
        if pattern is None:
            continue
        if not _volume_confirmed(bars, signal_index=signal_index, config=resolved_event_config):
            continue
        event = event_from_pattern_state(pattern, bars[signal_index], signal_index=signal_index)
        if event is None:
            continue
        events.append(event)
        last_event_index = signal_index

    return tuple(events)


def _volume_confirmed(
    bars: tuple[ResearchBar, ...],
    *,
    signal_index: int,
    config: ConsolidationEventConfig,
) -> bool:
    threshold = config.min_breakout_volume_ratio
    if threshold is None:
        return True
    if signal_index < config.volume_lookback_sessions:
        return False
    trailing = bars[signal_index - config.volume_lookback_sessions : signal_index]
    if any(item.volume < 0 for item in trailing) or bars[signal_index].volume < 0:
        return False
    average = sum(item.volume for item in trailing) / config.volume_lookback_sessions
    if average <= 0:
        return False
    return bars[signal_index].volume / average >= threshold
