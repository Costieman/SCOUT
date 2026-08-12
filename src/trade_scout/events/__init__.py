"""Discrete timestamped event generation and deduplication from pattern states."""

from trade_scout.events.consolidation_breakout import (
    ConsolidationBreakoutEvent,
    event_from_pattern_state,
)
from trade_scout.events.contracts import EventRecord

__all__ = ["ConsolidationBreakoutEvent", "EventRecord", "event_from_pattern_state"]
