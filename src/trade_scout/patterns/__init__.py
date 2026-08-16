"""Persistent structural pattern detection using upstream data/features."""

from trade_scout.patterns.consolidation_lifecycle import (
    ConsolidationLifecycleConfig,
    ConsolidationPatternTracker,
)
from trade_scout.patterns.consolidation_state import detect_qualified_patterns, qualified_pattern_at
from trade_scout.patterns.contracts import PatternLifecycleState, PatternState

__all__ = [
    "ConsolidationLifecycleConfig",
    "ConsolidationPatternTracker",
    "PatternLifecycleState",
    "PatternState",
    "detect_qualified_patterns",
    "qualified_pattern_at",
]
