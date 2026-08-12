"""Discrete consolidation-breakout events generated from qualified pattern state.

This module owns the event transition. It consumes already-qualified structural state
and the current signal bar, then emits a timestamped event record without inspecting
future outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import InstrumentId, QualityStatus, ResearchBar
from trade_scout.patterns import PatternLifecycleState, PatternState


@dataclass(frozen=True, slots=True)
class ConsolidationBreakoutEvent:
    """Close-confirmed upside breakout from a qualified consolidation pattern."""

    event_id: str
    instrument_id: InstrumentId
    signal_date: date
    signal_index: int
    pattern_instance_id: str
    trigger_boundary: float
    trigger_value: float
    dataset_version: str
    event_definition_version: str = "consolidation-close-breakout-v0.3"


def event_from_pattern_state(
    pattern: PatternState,
    signal_bar: ResearchBar,
    *,
    signal_index: int,
) -> ConsolidationBreakoutEvent | None:
    """Emit one close breakout event from a qualified point-in-time pattern state."""

    if pattern.state is not PatternLifecycleState.QUALIFIED:
        return None
    if pattern.instrument_id != signal_bar.instrument_id:
        raise ValueError("pattern and signal bar must reference the same instrument")
    if pattern.dataset_version != str(signal_bar.dataset_version):
        raise ValueError("pattern and signal bar must reference the same dataset version")
    if signal_bar.quality_status is not QualityStatus.PASS or not signal_bar.eligibility:
        return None

    boundary = pattern.structural_boundaries.get("resistance")
    if boundary is None:
        raise ValueError("qualified consolidation pattern requires a resistance boundary")
    if signal_bar.close <= boundary:
        return None

    return ConsolidationBreakoutEvent(
        event_id=(
            f"{signal_bar.instrument_id}:consolidation-close-breakout-v0.3:"
            f"{pattern.pattern_instance_id}:{signal_bar.trade_date.isoformat()}"
        ),
        instrument_id=signal_bar.instrument_id,
        signal_date=signal_bar.trade_date,
        signal_index=signal_index,
        pattern_instance_id=pattern.pattern_instance_id,
        trigger_boundary=boundary,
        trigger_value=signal_bar.close,
        dataset_version=str(signal_bar.dataset_version),
    )
