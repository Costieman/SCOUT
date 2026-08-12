"""Lifecycle projection joining immutable pattern states with generated events."""

from __future__ import annotations

from dataclasses import replace

from trade_scout.events.contracts import EventRecord
from trade_scout.patterns.contracts import PatternLifecycleState, PatternState


def project_consumed_pattern_states(
    states: tuple[PatternState, ...],
    events: tuple[EventRecord, ...],
) -> tuple[PatternState, ...]:
    """Mark an event's pattern instance CONSUMED from its signal date until that instance ends.

    Raw pattern detection remains event-independent. This projection is a downstream lifecycle
    view: once an EventRecord exists, that immutable pattern instance is closed as CONSUMED even
    when the breakout bar itself would make the rolling structural window fail qualification.
    A later detector-generated pattern instance is unaffected and begins a fresh lifecycle.
    """

    event_dates_by_instance = {event.pattern_instance_id: event.signal_date for event in events}
    projected: list[PatternState] = []

    for state in states:
        consumed_at = event_dates_by_instance.get(state.pattern_instance_id)
        if consumed_at is None or state.as_of_date < consumed_at:
            projected.append(state)
            continue
        projected.append(replace(state, state=PatternLifecycleState.CONSUMED))

    return tuple(projected)


__all__ = ["project_consumed_pattern_states"]
