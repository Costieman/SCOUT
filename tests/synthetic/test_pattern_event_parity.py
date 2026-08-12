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
from trade_scout.patterns.consolidation import ConsolidationDefinition, detect_consolidation_states
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    detect_consolidation_breakouts,
)
from trade_scout.patterns.trend import TrendFilter


def _bar(
    index: int,
    *,
    close: float,
    high: float | None = None,
    low: float | None = None,
    volume: float = 1_000_000.0,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_parity"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        close=close,
        volume=volume,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("synthetic-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _typed_events(
    bars: tuple[ResearchBar, ...],
    *,
    duration: int,
    max_range_pct: float,
    trend_filter: TrendFilter = TrendFilter.NONE,
    min_breakout_volume_ratio: float | None = None,
    volume_lookback_sessions: int = 20,
    cooldown_sessions: int = 0,
):
    states = detect_consolidation_states(
        bars,
        ConsolidationDefinition(
            duration_sessions=duration,
            max_range_pct=max_range_pct,
            trigger_ready_distance_pct=1.0,
        ),
    )
    return generate_close_breakout_events(
        bars,
        states,
        CloseBreakoutDefinition(
            trend_filter=trend_filter,
            min_breakout_volume_ratio=min_breakout_volume_ratio,
            volume_lookback_sessions=volume_lookback_sessions,
            cooldown_sessions=cooldown_sessions,
        ),
    )


def _exploratory_events(
    bars: tuple[ResearchBar, ...],
    *,
    duration: int,
    max_range_pct: float,
    trend_filter: TrendFilter = TrendFilter.NONE,
    min_breakout_volume_ratio: float | None = None,
    volume_lookback_sessions: int = 20,
    cooldown_sessions: int = 0,
):
    return detect_consolidation_breakouts(
        bars,
        ConsolidationBreakoutConfig(
            duration=duration,
            max_range_pct=max_range_pct,
            trend_filter=trend_filter,
            min_breakout_volume_ratio=min_breakout_volume_ratio,
            volume_lookback_sessions=volume_lookback_sessions,
            cooldown_sessions=cooldown_sessions,
        ),
    )


def _assert_event_parity(exploratory, typed) -> None:
    assert tuple(item.signal_date for item in typed) == tuple(
        item.signal_date for item in exploratory
    )
    assert tuple(item.trigger_boundary for item in typed) == tuple(
        item.boundary for item in exploratory
    )
    assert tuple(item.trigger_value for item in typed) == tuple(
        item.signal_close for item in exploratory
    )


def test_simple_close_breakout_event_set_matches_exploratory_detector() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
    )

    exploratory = _exploratory_events(bars, duration=10, max_range_pct=0.03)
    typed = _typed_events(bars, duration=10, max_range_pct=0.03)

    _assert_event_parity(exploratory, typed)


def test_trend_filtered_event_set_matches_exploratory_detector() -> None:
    bars = tuple(
        [_bar(index, close=80.0 + index * 0.1) for index in range(200)]
        + [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(200, 210)]
        + [_bar(210, close=102.0, high=102.5, low=100.5)]
    )

    exploratory = _exploratory_events(
        bars,
        duration=10,
        max_range_pct=0.03,
        trend_filter=TrendFilter.ABOVE_SMA_200,
    )
    typed = _typed_events(
        bars,
        duration=10,
        max_range_pct=0.03,
        trend_filter=TrendFilter.ABOVE_SMA_200,
    )

    _assert_event_parity(exploratory, typed)


def test_volume_filtered_event_set_matches_exploratory_detector() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5, volume=1_600_000.0)]
    )

    exploratory = _exploratory_events(
        bars,
        duration=10,
        max_range_pct=0.03,
        min_breakout_volume_ratio=1.5,
        volume_lookback_sessions=10,
    )
    typed = _typed_events(
        bars,
        duration=10,
        max_range_pct=0.03,
        min_breakout_volume_ratio=1.5,
        volume_lookback_sessions=10,
    )

    _assert_event_parity(exploratory, typed)


def test_typed_engine_intentionally_deduplicates_unchanged_pattern_instance() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(index, close=102.0, high=102.5, low=100.5) for index in range(10, 20)]
    )

    exploratory = _exploratory_events(
        bars,
        duration=10,
        max_range_pct=0.05,
        cooldown_sessions=0,
    )
    typed = _typed_events(
        bars,
        duration=10,
        max_range_pct=0.05,
        cooldown_sessions=0,
    )

    assert len(typed) <= 1
    assert len(exploratory) >= len(typed)
