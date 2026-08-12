from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events.breakout import generate_close_breakout_events
from trade_scout.patterns.consolidation import ConsolidationDefinition, detect_consolidation_states
from trade_scout.patterns.consolidation_breakout import TrendFilter as ExploratoryTrendFilter
from trade_scout.patterns.contracts import PatternLifecycleState
from trade_scout.patterns.trend import TrendFilter


def _bar(
    index: int,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
    quality_status: QualityStatus = QualityStatus.PASS,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_synthetic"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=quality_status,
        dataset_version=DatasetVersion("synthetic-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _definition() -> ConsolidationDefinition:
    return ConsolidationDefinition(
        duration_sessions=10,
        max_range_pct=0.03,
        trigger_ready_distance_pct=0.02,
    )


def test_flat_base_becomes_trigger_ready_with_stable_instance_identity() -> None:
    bars = tuple(_bar(index, close=100.0, high=101.0, low=99.0) for index in range(14))

    states = detect_consolidation_states(bars, _definition())

    assert states[8].state is PatternLifecycleState.FORMING
    assert states[9].state is PatternLifecycleState.TRIGGER_READY
    assert states[13].state is PatternLifecycleState.TRIGGER_READY
    assert states[9].pattern_instance_id == states[13].pattern_instance_id
    assert states[9].formation_start == bars[0].trade_date


def test_wide_range_invalidates_an_active_pattern() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=100.0, high=106.0, low=99.0)]
    )

    states = detect_consolidation_states(bars, _definition())

    assert states[9].state is PatternLifecycleState.TRIGGER_READY
    assert states[10].state is PatternLifecycleState.INVALIDATED
    assert states[10].pattern_instance_id == states[9].pattern_instance_id


def test_breakout_uses_prior_pattern_boundary_and_emits_once() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
        + [_bar(11, close=103.0, high=103.5, low=102.0)]
    )
    states = detect_consolidation_states(bars, _definition())

    events = generate_close_breakout_events(bars, states)

    assert len(events) == 1
    assert events[0].signal_date == bars[10].trade_date
    assert events[0].trigger_boundary == 101.0
    assert events[0].trigger_value == 102.0
    assert events[0].pattern_instance_id == states[9].pattern_instance_id


def test_quarantined_trigger_bar_cannot_generate_event() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [
            _bar(
                10,
                close=102.0,
                high=102.5,
                low=100.5,
                quality_status=QualityStatus.QUARANTINE,
            )
        ]
    )
    states = detect_consolidation_states(bars, _definition())

    assert generate_close_breakout_events(bars, states) == ()


def test_future_bar_changes_do_not_change_existing_event_identity() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
        + [_bar(index, close=103.0) for index in range(11, 20)]
    )
    states = detect_consolidation_states(bars, _definition())
    original = generate_close_breakout_events(bars, states)[0]
    changed = list(bars)
    changed[15:] = [
        replace(item, open=500.0, high=505.0, low=495.0, close=500.0) for item in changed[15:]
    ]
    changed_bars = tuple(changed)
    changed_states = detect_consolidation_states(changed_bars, _definition())

    after = generate_close_breakout_events(changed_bars, changed_states)[0]

    assert after.event_id == original.event_id
    assert after.trigger_boundary == original.trigger_boundary
    assert after.signal_date == original.signal_date


def test_prefix_recomputation_matches_batch_state_and_event() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
        + [_bar(index, close=103.0) for index in range(11, 16)]
    )
    definition = _definition()
    batch_states = detect_consolidation_states(bars, definition)
    batch_events = generate_close_breakout_events(bars, batch_states)

    for end in range(1, len(bars) + 1):
        prefix = bars[:end]
        prefix_states = detect_consolidation_states(prefix, definition)
        assert prefix_states[-1] == batch_states[end - 1]

    prefix_states = detect_consolidation_states(bars[:11], definition)
    prefix_events = generate_close_breakout_events(bars[:11], prefix_states)
    assert prefix_events == batch_events


def test_typed_engine_reuses_exploratory_trend_filter_contract() -> None:
    assert ExploratoryTrendFilter is TrendFilter

    qualifying_bars = tuple(
        [_bar(index, close=80.0 + index * 0.1) for index in range(195)]
        + [_bar(index, close=100.5, high=101.0, low=100.0) for index in range(195, 205)]
    )
    blocked_bars = tuple(
        [_bar(index, close=110.0) for index in range(195)]
        + [_bar(index, close=100.0, high=100.5, low=99.5) for index in range(195, 205)]
    )
    definition = ConsolidationDefinition(
        duration_sessions=10,
        max_range_pct=0.03,
        trigger_ready_distance_pct=0.02,
        trend_filter=TrendFilter.ABOVE_SMA_200,
    )

    qualifying = detect_consolidation_states(qualifying_bars, definition)
    blocked = detect_consolidation_states(blocked_bars, definition)

    assert qualifying[-1].state is PatternLifecycleState.TRIGGER_READY
    assert blocked[-1].state is PatternLifecycleState.NONE
    assert any(
        item.name == "trend_filter" and item.value == TrendFilter.ABOVE_SMA_200.value
        for item in qualifying[-1].resolved_parameters
    )
