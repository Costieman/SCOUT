"""Scanner replay adapter for the canonical consolidation Pattern/Event pipeline.

This adapter does not reimplement pattern or event logic. It replays the exact incremental research
pipeline through the requested as-of session and projects its current lifecycle output into the
stable scanner candidate contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import CorporateActionRecord, QualityStatus, ResearchBar
from trade_scout.events import (
    ConsolidationEventConfig,
    replay_consolidation_pipeline,
)
from trade_scout.patterns import ConsolidationLifecycleConfig, PatternLifecycleState, PatternState
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig
from trade_scout.patterns.consolidation_state import FEATURE_SET_VERSION
from trade_scout.scanner.contracts import (
    ReplayObservation,
    ScanCandidateState,
    SnapshotField,
    StructuralLevel,
)


@dataclass(frozen=True, slots=True)
class ConsolidationReplayEvaluator:
    """Project canonical consolidation lifecycle/event state into historical scanner replay."""

    pattern_config: ConsolidationBreakoutConfig
    event_config: ConsolidationEventConfig | None = None
    lifecycle_config: ConsolidationLifecycleConfig | None = None
    corporate_actions: tuple[CorporateActionRecord, ...] = ()

    @property
    def feature_set_version(self) -> str:
        """Return the exact feature-set identity emitted by the shared pattern implementation."""

        return FEATURE_SET_VERSION

    def evaluate(
        self,
        bars: tuple[ResearchBar, ...],
        *,
        as_of_date: date,
    ) -> ReplayObservation | None:
        """Replay shared research logic through one historical session and project current state."""

        if not bars or bars[-1].trade_date != as_of_date:
            raise ValueError("consolidation replay evaluator requires history through as_of_date")
        instrument_id = bars[-1].instrument_id
        actions = tuple(
            action
            for action in self.corporate_actions
            if action.instrument_id == instrument_id and action.effective_date <= as_of_date
        )
        replay = replay_consolidation_pipeline(
            bars,
            self.pattern_config,
            event_config=self.event_config,
            lifecycle_config=self.lifecycle_config,
            corporate_actions=actions,
        )
        event = next(
            (item for item in reversed(replay.events) if item.signal_date == as_of_date),
            None,
        )
        states_today = tuple(
            item for item in replay.pattern_states if item.as_of_date == as_of_date
        )
        if event is not None:
            pattern = _pattern_for_event(states_today, event.pattern_instance_id)
            return _observation(
                bars[-1],
                pattern,
                candidate_state=ScanCandidateState.TRIGGERED,
                event_id=event.event_id,
                reasons=("registered breakout event occurred on replay session",),
            )
        if not states_today:
            return None

        pattern = states_today[-1]
        candidate_state = _scanner_state(pattern.state)
        if candidate_state is None:
            return None
        reason = f"canonical pattern lifecycle state is {pattern.state.value}"
        invalidation = pattern.resolved_parameters.get("invalidation_reason")
        reasons = (reason,)
        if isinstance(invalidation, str) and invalidation.strip():
            reasons = (reason, f"invalidation reason: {invalidation}")
        return _observation(
            bars[-1],
            pattern,
            candidate_state=candidate_state,
            event_id=None,
            reasons=reasons,
        )


def _pattern_for_event(
    states_today: tuple[PatternState, ...],
    pattern_instance_id: str,
) -> PatternState:
    matches = tuple(
        state for state in states_today if state.pattern_instance_id == pattern_instance_id
    )
    if not matches:
        raise RuntimeError("replayed event has no same-session pattern state")
    return matches[0]


def _scanner_state(state: PatternLifecycleState) -> ScanCandidateState | None:
    mapping = {
        PatternLifecycleState.FORMING: ScanCandidateState.FORMING,
        PatternLifecycleState.QUALIFIED: ScanCandidateState.QUALIFIED,
        PatternLifecycleState.TRIGGER_READY: ScanCandidateState.TRIGGER_READY,
        PatternLifecycleState.INVALIDATED: ScanCandidateState.INVALIDATED,
    }
    return mapping.get(state)


def _observation(
    bar: ResearchBar,
    pattern: PatternState,
    *,
    candidate_state: ScanCandidateState,
    event_id: str | None,
    reasons: tuple[str, ...],
) -> ReplayObservation:
    if pattern.feature_set_version != FEATURE_SET_VERSION:
        raise ValueError("consolidation pattern emitted unexpected feature-set version")
    features = [
        SnapshotField("close", bar.close),
        SnapshotField("volume", bar.volume),
    ]
    base_range = pattern.resolved_parameters.get("base_range_pct")
    if isinstance(base_range, int | float) and not isinstance(base_range, bool):
        features.append(SnapshotField("base_range_pct", float(base_range)))
    structural_levels = tuple(
        StructuralLevel(name, value)
        for name, value in sorted(pattern.structural_boundaries.items())
    )
    return ReplayObservation(
        source_date=bar.trade_date,
        pattern_instance_id=pattern.pattern_instance_id,
        candidate_state=candidate_state,
        feature_snapshot=tuple(features),
        structural_levels=structural_levels,
        quality_status=QualityStatus.PASS,
        event_id=event_id,
        reasons=reasons,
    )
