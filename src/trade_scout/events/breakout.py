"""Close-confirmed breakout events generated from prior pattern state only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.patterns.contracts import (
    PatternLifecycleState,
    PatternState,
    ResolvedPatternParameter,
)


@dataclass(frozen=True, slots=True)
class CloseBreakoutDefinition:
    """Resolved close-breakout event definition."""

    event_type: str = "upside_close_breakout"
    event_version: str = "upside-close-breakout-v0.1"


def generate_close_breakout_events(
    bars: tuple[ResearchBar, ...],
    states: tuple[PatternState, ...],
    definition: CloseBreakoutDefinition | None = None,
) -> tuple[EventRecord, ...]:
    """Generate at most one close breakout per qualified pattern instance.

    The trigger on session t is evaluated against the resistance boundary stored in the pattern
    state from session t-1, preventing the trigger bar from redefining its own boundary.
    """

    if len(bars) != len(states):
        raise ValueError("bars and states must have identical lengths")
    if not bars:
        return ()
    if definition is None:
        definition = CloseBreakoutDefinition()

    events: list[EventRecord] = []
    consumed_instances: set[str] = set()
    eligible_states = {PatternLifecycleState.QUALIFIED, PatternLifecycleState.TRIGGER_READY}

    for index in range(1, len(bars)):
        bar = bars[index]
        prior = states[index - 1]
        if prior.state not in eligible_states:
            continue
        if prior.pattern_instance_id in consumed_instances:
            continue
        if not bar.eligibility or bar.quality_status is not QualityStatus.PASS:
            continue
        boundary = _boundary(prior, "resistance")
        if boundary is None or bar.close <= boundary:
            continue

        event_id = _stable_id(
            "evt",
            {
                "instrument_id": str(bar.instrument_id),
                "event_version": definition.event_version,
                "pattern_instance_id": prior.pattern_instance_id,
                "signal_date": bar.trade_date.isoformat(),
                "trigger_boundary": f"{boundary:.12g}",
            },
        )
        events.append(
            EventRecord(
                event_id=event_id,
                instrument_id=bar.instrument_id,
                event_type=definition.event_type,
                event_version=definition.event_version,
                pattern_instance_id=prior.pattern_instance_id,
                signal_date=bar.trade_date,
                knowledge_time=None,
                earliest_execution_time=None,
                trigger_value=bar.close,
                trigger_boundary=boundary,
                resolved_parameters=(
                    ResolvedPatternParameter("confirmation", "daily_close"),
                    ResolvedPatternParameter("boundary_source", "prior_pattern_state"),
                ),
                event_family_id=prior.pattern_instance_id,
                feature_set_version=prior.feature_set_version,
                dataset_version=bar.dataset_version,
                quality_status=bar.quality_status,
            )
        )
        consumed_instances.add(prior.pattern_instance_id)

    return tuple(events)


def _boundary(state: PatternState, name: str) -> float | None:
    for boundary in state.structural_boundaries:
        if boundary.name == name:
            return boundary.value
    return None


def _stable_id(prefix: str, payload: dict[str, str]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:24]}"
