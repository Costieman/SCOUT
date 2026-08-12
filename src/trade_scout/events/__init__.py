"""Discrete timestamped event generation and deduplication from pattern states."""

from trade_scout.events.consolidation_breakout import (
    ConsolidationBreakoutEvent,
    event_from_pattern_state,
)
from trade_scout.events.consolidation_pipeline import (
    ConsolidationEventConfig,
    detect_consolidation_events,
)
from trade_scout.events.contracts import EventRecord

__all__ = [
    "ConsolidationBreakoutEvent",
    "ConsolidationEventConfig",
    "EventRecord",
    "detect_consolidation_events",
    "event_from_pattern_state",
]
