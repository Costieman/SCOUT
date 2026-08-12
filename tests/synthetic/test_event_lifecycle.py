from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events.breakout import CloseBreakoutDefinition, generate_close_breakout_events
from trade_scout.events.lifecycle import project_consumed_pattern_states
from trade_scout.patterns.consolidation import ConsolidationDefinition, detect_consolidation_states
from trade_scout.patterns.contracts import PatternLifecycleState


def _bar(
    index: int,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_lifecycle"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("synthetic-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _definition() -> ConsolidationDefinition:
    return ConsolidationDefinition(
        duration_sessions=10,
        max_range_pct=0.03,
        trigger_ready_distance_pct=0.02,
    )


def test_breakout_projects_parent_pattern_to_consumed() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
    )
    states = detect_consolidation_states(bars, _definition())
    events = generate_close_breakout_events(bars, states)

    projected = project_consumed_pattern_states(states, events)

    assert len(events) == 1
    assert projected[9].state is PatternLifecycleState.TRIGGER_READY
    assert projected[10].pattern_instance_id == events[0].pattern_instance_id
    assert projected[10].state is PatternLifecycleState.CONSUMED


def test_new_pattern_instance_can_trigger_after_reset() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
        + [_bar(11, close=100.0, high=110.0, low=99.0)]
        + [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(12, 22)]
        + [_bar(22, close=102.0, high=102.5, low=100.5)]
    )
    states = detect_consolidation_states(bars, _definition())

    events = generate_close_breakout_events(bars, states)

    assert len(events) == 2
    assert events[0].pattern_instance_id != events[1].pattern_instance_id


def test_cooldown_can_suppress_distinct_new_pattern_event() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
        + [_bar(11, close=100.0, high=110.0, low=99.0)]
        + [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(12, 22)]
        + [_bar(22, close=102.0, high=102.5, low=100.5)]
    )
    states = detect_consolidation_states(bars, _definition())
    event_definition = CloseBreakoutDefinition(cooldown_sessions=20)

    events = generate_close_breakout_events(bars, states, event_definition)

    assert len(events) == 1
    assert any(
        item.name == "cooldown_sessions" and item.value == "20"
        for item in events[0].resolved_parameters
    )
