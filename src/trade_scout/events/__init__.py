"""Discrete timestamped event generation and deduplication from pattern states."""

from trade_scout.events.consolidation_breakout import (
    ConsolidationBreakoutEvent,
    event_from_pattern_state,
)
from trade_scout.events.consolidation_pipeline import (
    ConsolidationEventConfig,
    ConsolidationPipelineReplay,
    ConsolidationPipelineUpdate,
    IncrementalConsolidationPipeline,
    detect_consolidation_events,
    replay_consolidation_pipeline,
)
from trade_scout.events.contracts import EventRecord

__all__ = [
    "ConsolidationBreakoutEvent",
    "ConsolidationEventConfig",
    "ConsolidationPipelineReplay",
    "ConsolidationPipelineUpdate",
    "EventRecord",
    "IncrementalConsolidationPipeline",
    "detect_consolidation_events",
    "event_from_pattern_state",
    "replay_consolidation_pipeline",
]
