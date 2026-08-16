"""Application of production-eligible definitions to current market data."""

from trade_scout.scanner.consolidation_replay import ConsolidationReplayEvaluator
from trade_scout.scanner.contracts import (
    CandidateStateCount,
    HistoricalReplayResult,
    ReplayInstrumentRecord,
    ReplayInstrumentStatus,
    ReplayObservation,
    ReplayPublicationClass,
    ScanCandidate,
    ScanCandidateState,
    ScannerMode,
    ScanStrategyDefinition,
    SnapshotField,
    StructuralLevel,
    strategy_from_research_evidence,
)
from trade_scout.scanner.replay import (
    ReplayEvaluator,
    ScannerEligibilityError,
    run_historical_replay,
)

__all__ = [
    "CandidateStateCount",
    "ConsolidationReplayEvaluator",
    "HistoricalReplayResult",
    "ReplayEvaluator",
    "ReplayInstrumentRecord",
    "ReplayInstrumentStatus",
    "ReplayObservation",
    "ReplayPublicationClass",
    "ScanCandidate",
    "ScanCandidateState",
    "ScanStrategyDefinition",
    "ScannerEligibilityError",
    "ScannerMode",
    "SnapshotField",
    "StructuralLevel",
    "run_historical_replay",
    "strategy_from_research_evidence",
]
