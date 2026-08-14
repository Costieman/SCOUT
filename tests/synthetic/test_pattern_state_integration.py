from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events import (
    ConsolidationEventConfig,
    IncrementalConsolidationPipeline,
    replay_consolidation_pipeline,
)
from trade_scout.patterns import (
    ConsolidationLifecycleConfig,
    PatternLifecycleState,
    qualified_pattern_at,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.synthetic import (
    SyntheticAnnotationKind,
    consolidation_breakout_scenario,
    false_breakout_scenario,
    nested_bases_scenario,
    split_discontinuity_scenario,
)


def _config(*, duration: int, max_range_pct: float, cooldown_sessions: int = 5) -> ConsolidationBreakoutConfig:
    return ConsolidationBreakoutConfig(
        duration=duration,
        max_range_pct=max_range_pct,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=cooldown_sessions,
    )


def _bar(index: int, *, close: float, high: float, low: float) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("SYN-LIFECYCLE"),
        trade_date=date(2024, 1, 2) + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("synthetic-lifecycle-test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _state_signature(state: object) -> object:
    return state


def test_synthetic_breakout_moves_from_trigger_ready_to_consumed_once() -> None:
    scenario = consolidation_breakout_scenario()
    breakout = next(
        annotation
        for annotation in scenario.annotations
        if annotation.kind is SyntheticAnnotationKind.BREAKOUT
    )
    replay = replay_consolidation_pipeline(
        scenario.raw_bars,
        _config(duration=10, max_range_pct=0.04),
    )

    assert any(
        state.state is PatternLifecycleState.TRIGGER_READY for state in replay.pattern_states
    )
    assert len(replay.events) == 1
    assert replay.events[0].signal_date == breakout.start_date
    consumed = [
        state for state in replay.pattern_states if state.state is PatternLifecycleState.CONSUMED
    ]
    assert len(consumed) == 1
    assert consumed[0].pattern_instance_id == replay.events[0].pattern_instance_id


def test_nested_synthetic_bases_remain_independent_pattern_instances() -> None:
    scenario = nested_bases_scenario()
    breakout = next(
        annotation
        for annotation in scenario.annotations
        if annotation.kind is SyntheticAnnotationKind.BREAKOUT
    )
    signal_index = next(
        index for index, bar in enumerate(scenario.raw_bars) if bar.trade_date == breakout.start_date
    )

    inner = qualified_pattern_at(
        scenario.raw_bars,
        signal_index=signal_index,
        config=_config(duration=10, max_range_pct=0.06),
    )
    outer = qualified_pattern_at(
        scenario.raw_bars,
        signal_index=signal_index,
        config=_config(duration=25, max_range_pct=0.06),
    )

    assert inner is not None
    assert outer is not None
    assert inner.pattern_instance_id != outer.pattern_instance_id
    assert inner.formation_start > outer.formation_start
    assert inner.formation_end == outer.formation_end
    assert inner.resolved_parameters["duration"] == 10
    assert outer.resolved_parameters["duration"] == 25


def test_invalidation_requires_reset_and_wholly_new_base_before_next_event() -> None:
    initial_base = tuple(_bar(index, close=100.0, high=102.0, low=98.0) for index in range(5))
    trigger_ready = _bar(5, close=101.0, high=102.0, low=99.0)
    invalidation = _bar(6, close=97.0, high=101.0, low=96.0)
    new_base = tuple(_bar(index, close=110.0, high=111.0, low=109.0) for index in range(7, 12))
    breakout = _bar(12, close=112.0, high=113.0, low=111.0)
    bars = (*initial_base, trigger_ready, invalidation, *new_base, breakout)

    replay = replay_consolidation_pipeline(
        bars,
        _config(duration=5, max_range_pct=0.05, cooldown_sessions=2),
        lifecycle_config=ConsolidationLifecycleConfig(
            trigger_ready_distance_pct=0.02,
            reset_sessions=2,
        ),
    )

    invalidated = [
        state for state in replay.pattern_states if state.state is PatternLifecycleState.INVALIDATED
    ]
    assert len(invalidated) == 1
    assert invalidated[0].as_of_date == invalidation.trade_date
    assert invalidated[0].resolved_parameters["invalidation_reason"] == "closed_below_support"
    assert len(replay.events) == 1
    assert replay.events[0].signal_date == breakout.trade_date
    event_pattern = next(
        state
        for state in replay.pattern_states
        if state.pattern_instance_id == replay.events[0].pattern_instance_id
    )
    assert event_pattern.formation_start > invalidation.trade_date


def test_corporate_action_invalidates_active_episode_and_prevents_bridge_across_split() -> None:
    scenario = split_discontinuity_scenario()
    split_date = scenario.corporate_actions[0].effective_date
    replay = replay_consolidation_pipeline(
        scenario.raw_bars,
        _config(duration=5, max_range_pct=0.20, cooldown_sessions=2),
        event_config=ConsolidationEventConfig(
            cooldown_sessions=2,
            min_breakout_volume_ratio=10.0,
            volume_lookback_sessions=5,
        ),
        lifecycle_config=ConsolidationLifecycleConfig(reset_sessions=2),
        corporate_actions=scenario.corporate_actions,
    )

    split_state = next(
        state
        for state in replay.pattern_states
        if state.as_of_date == split_date and state.state is PatternLifecycleState.INVALIDATED
    )
    assert split_state.resolved_parameters["invalidation_reason"] == "corporate_action_discontinuity"
    assert replay.events == ()
    later_states = [state for state in replay.pattern_states if state.as_of_date > split_date]
    assert all(state.formation_start > split_date for state in later_states)


def test_false_breakout_event_is_unchanged_by_later_failure() -> None:
    scenario = false_breakout_scenario()
    failure = next(
        annotation
        for annotation in scenario.annotations
        if annotation.kind is SyntheticAnnotationKind.FALSE_BREAKOUT
    )
    breakout_date = failure.start_date
    breakout_index = next(
        index for index, bar in enumerate(scenario.raw_bars) if bar.trade_date == breakout_date
    )
    config = _config(duration=20, max_range_pct=0.05)

    prefix = replay_consolidation_pipeline(scenario.raw_bars[: breakout_index + 1], config)
    full = replay_consolidation_pipeline(scenario.raw_bars, config)

    assert len(prefix.events) == 1
    assert full.events[0] == prefix.events[0]
    assert full.events[0].signal_date == breakout_date


def test_batch_replay_matches_incremental_updates_exactly() -> None:
    scenario = consolidation_breakout_scenario()
    config = _config(duration=10, max_range_pct=0.04)
    batch = replay_consolidation_pipeline(scenario.raw_bars, config)

    engine = IncrementalConsolidationPipeline(config)
    incremental_states = []
    incremental_events = []
    for bar in scenario.raw_bars:
        update = engine.update(bar)
        incremental_states.extend(update.pattern_states)
        if update.event is not None:
            incremental_events.append(update.event)

    assert tuple(incremental_states) == batch.pattern_states
    assert tuple(incremental_events) == batch.events


def test_future_bars_cannot_rewrite_prior_pattern_state_history() -> None:
    scenario = consolidation_breakout_scenario()
    config = _config(duration=10, max_range_pct=0.04)
    cutoff = 35
    prefix = replay_consolidation_pipeline(scenario.raw_bars[:cutoff], config)
    full = replay_consolidation_pipeline(scenario.raw_bars, config)
    cutoff_date = scenario.raw_bars[cutoff - 1].trade_date

    full_prior_states = tuple(
        state for state in full.pattern_states if state.as_of_date <= cutoff_date
    )
    full_prior_events = tuple(event for event in full.events if event.signal_date <= cutoff_date)
    assert tuple(_state_signature(state) for state in prefix.pattern_states) == tuple(
        _state_signature(state) for state in full_prior_states
    )
    assert prefix.events == full_prior_events
