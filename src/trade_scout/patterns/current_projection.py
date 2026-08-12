"""Latest-session projection for typed pattern/event research surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.events.breakout import CloseBreakoutDefinition, generate_close_breakout_events
from trade_scout.features.volume import relative_volume
from trade_scout.patterns.contracts import PatternLifecycleState, PatternState
from trade_scout.patterns.trend import trend_qualified


@dataclass(frozen=True, slots=True)
class CurrentPatternProjection:
    """Surface-friendly latest view without collapsing structure and signal semantics."""

    as_of_date: date
    status: str
    structural_state: PatternLifecycleState
    structural_pattern_instance_id: str
    signal_pattern_instance_id: str | None
    trigger_boundary: float | None
    distance_to_trigger_pct: float | None
    trend_qualified: bool
    breakout_volume_ratio: float | None
    latest_event_id: str | None
    message: str


def project_latest_pattern_state(
    bars: tuple[ResearchBar, ...],
    states: tuple[PatternState, ...],
    event_definition: CloseBreakoutDefinition | None = None,
) -> CurrentPatternProjection:
    """Project latest structural state and current trigger evaluation side by side."""

    if len(bars) != len(states):
        raise ValueError("bars and states must have identical lengths")
    if not bars:
        raise ValueError("at least one bar/state pair is required")
    definition = event_definition or CloseBreakoutDefinition()

    latest_index = len(bars) - 1
    latest = bars[latest_index]
    structural = states[latest_index]
    prior = states[latest_index - 1] if latest_index else None
    eligible_states = {PatternLifecycleState.QUALIFIED, PatternLifecycleState.TRIGGER_READY}
    signal_pattern = prior if prior is not None and prior.state in eligible_states else None
    boundary = _boundary(signal_pattern, "resistance") if signal_pattern is not None else None
    trend_ok = trend_qualified(bars, latest_index, definition.trend_filter)
    volume_ratio = relative_volume(
        bars,
        signal_index=latest_index,
        lookback_sessions=definition.volume_lookback_sessions,
    )
    events = generate_close_breakout_events(bars, states, definition)
    latest_event = next(
        (event for event in reversed(events) if event.signal_date == latest.trade_date),
        None,
    )
    distance = None if boundary is None else (boundary - latest.close) / boundary

    if latest_event is not None:
        status = "BREAKOUT"
        message = "Latest session generated a typed breakout event from the prior pattern state."
    elif not latest.eligibility or latest.quality_status is not QualityStatus.PASS:
        status = "QUALITY_BLOCKED"
        message = "Latest session cannot generate a normal event because eligibility/quality failed."
    elif signal_pattern is not None and boundary is not None:
        volume_ok = definition.min_breakout_volume_ratio is None or (
            volume_ratio is not None and volume_ratio >= definition.min_breakout_volume_ratio
        )
        if not trend_ok:
            status = "TREND_FILTER_FAIL"
            message = "Prior structure is available, but the signal-session trend gate is not met."
        elif latest.close > boundary and not volume_ok:
            status = "VOLUME_FILTER_FAIL"
            message = "Price crossed the prior boundary, but the configured volume gate is not met."
        elif latest.close > boundary:
            status = "TRIGGER_BLOCKED"
            message = "Price crossed the prior boundary without producing a canonical event."
        else:
            status = "TRIGGER_READY"
            message = "Prior structure is active and the latest close remains below its stored boundary."
    elif structural.state is PatternLifecycleState.FORMING:
        status = "FORMING"
        message = "The structural detector is still accumulating the required formation history."
    elif structural.state in {PatternLifecycleState.QUALIFIED, PatternLifecycleState.TRIGGER_READY}:
        status = "STRUCTURE_ACTIVE"
        message = "A typed structure is active; no prior-session trigger boundary is available yet."
    else:
        status = "INACTIVE"
        message = "No prior qualified pattern state is available for a current breakout trigger."

    return CurrentPatternProjection(
        as_of_date=latest.trade_date,
        status=status,
        structural_state=structural.state,
        structural_pattern_instance_id=structural.pattern_instance_id,
        signal_pattern_instance_id=(
            None if signal_pattern is None else signal_pattern.pattern_instance_id
        ),
        trigger_boundary=boundary,
        distance_to_trigger_pct=distance,
        trend_qualified=trend_ok,
        breakout_volume_ratio=volume_ratio,
        latest_event_id=None if latest_event is None else latest_event.event_id,
        message=message,
    )


def _boundary(state: PatternState | None, name: str) -> float | None:
    if state is None:
        return None
    for boundary in state.structural_boundaries:
        if boundary.name == name:
            return boundary.value
    return None
