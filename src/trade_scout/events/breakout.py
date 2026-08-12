"""Close-confirmed breakout events generated from prior pattern state only."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from trade_scout.data.contracts import QualityStatus, ResearchBar
from trade_scout.events.contracts import EventRecord
from trade_scout.features.volume import relative_volume
from trade_scout.patterns.contracts import (
    PatternLifecycleState,
    PatternState,
    ResolvedPatternParameter,
)
from trade_scout.patterns.trend import TrendFilter, trend_qualified


@dataclass(frozen=True, slots=True)
class CloseBreakoutDefinition:
    """Resolved close-breakout event definition."""

    trend_filter: TrendFilter = TrendFilter.NONE
    min_breakout_volume_ratio: float | None = None
    volume_lookback_sessions: int = 20
    cooldown_sessions: int = 0
    event_type: str = "upside_close_breakout"
    event_version: str = "upside-close-breakout-v0.4"

    def __post_init__(self) -> None:
        if self.min_breakout_volume_ratio is not None and self.min_breakout_volume_ratio <= 0:
            raise ValueError("min_breakout_volume_ratio must be positive when supplied")
        if not 2 <= self.volume_lookback_sessions <= 252:
            raise ValueError("volume_lookback_sessions must be between 2 and 252")
        if not 0 <= self.cooldown_sessions <= 252:
            raise ValueError("cooldown_sessions must be between 0 and 252")


def generate_close_breakout_events(
    bars: tuple[ResearchBar, ...],
    states: tuple[PatternState, ...],
    definition: CloseBreakoutDefinition | None = None,
) -> tuple[EventRecord, ...]:
    """Generate at most one close breakout per qualified pattern instance.

    The trigger on session t is evaluated against the resistance boundary stored in the pattern
    state from session t-1, preventing the trigger bar from redefining its own boundary. Optional
    trend and volume context are evaluated on the breakout session itself. Cooldown is applied only
    between distinct pattern instances; it never permits repeated events from one unchanged base.
    """

    if len(bars) != len(states):
        raise ValueError("bars and states must have identical lengths")
    if not bars:
        return ()
    if definition is None:
        definition = CloseBreakoutDefinition()

    events: list[EventRecord] = []
    consumed_instances: set[str] = set()
    last_event_index: int | None = None
    eligible_states = {PatternLifecycleState.QUALIFIED, PatternLifecycleState.TRIGGER_READY}

    for index in range(1, len(bars)):
        bar = bars[index]
        prior = states[index - 1]
        if prior.state not in eligible_states:
            continue
        if prior.pattern_instance_id in consumed_instances:
            continue
        if last_event_index is not None and index - last_event_index <= definition.cooldown_sessions:
            continue
        if not bar.eligibility or bar.quality_status is not QualityStatus.PASS:
            continue
        boundary = _boundary(prior, "resistance")
        if boundary is None or bar.close <= boundary:
            continue
        if not trend_qualified(bars, index, definition.trend_filter):
            continue

        volume_ratio = relative_volume(
            bars,
            signal_index=index,
            lookback_sessions=definition.volume_lookback_sessions,
        )
        if definition.min_breakout_volume_ratio is not None and (
            volume_ratio is None or volume_ratio < definition.min_breakout_volume_ratio
        ):
            continue

        volume_gate = (
            "none"
            if definition.min_breakout_volume_ratio is None
            else f"{definition.min_breakout_volume_ratio:.12g}"
        )
        event_id = _stable_id(
            "evt",
            {
                "instrument_id": str(bar.instrument_id),
                "event_version": definition.event_version,
                "pattern_instance_id": prior.pattern_instance_id,
                "signal_date": bar.trade_date.isoformat(),
                "trigger_boundary": f"{boundary:.12g}",
                "trend_filter": definition.trend_filter.value,
                "volume_gate": volume_gate,
                "volume_lookback_sessions": str(definition.volume_lookback_sessions),
                "cooldown_sessions": str(definition.cooldown_sessions),
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
                    ResolvedPatternParameter("trend_filter", definition.trend_filter.value),
                    ResolvedPatternParameter("min_breakout_volume_ratio", volume_gate),
                    ResolvedPatternParameter(
                        "volume_lookback_sessions", str(definition.volume_lookback_sessions)
                    ),
                    ResolvedPatternParameter(
                        "observed_breakout_volume_ratio",
                        "unavailable" if volume_ratio is None else f"{volume_ratio:.12g}",
                    ),
                    ResolvedPatternParameter("cooldown_sessions", str(definition.cooldown_sessions)),
                ),
                event_family_id=prior.pattern_instance_id,
                feature_set_version=prior.feature_set_version,
                dataset_version=bar.dataset_version,
                quality_status=bar.quality_status,
            )
        )
        consumed_instances.add(prior.pattern_instance_id)
        last_event_index = index

    return tuple(events)


def _boundary(state: PatternState, name: str) -> float | None:
    for boundary in state.structural_boundaries:
        if boundary.name == name:
            return boundary.value
    return None


def _stable_id(prefix: str, payload: dict[str, str]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:24]}"
