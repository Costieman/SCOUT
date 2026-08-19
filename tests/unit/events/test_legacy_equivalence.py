from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events import detect_consolidation_events
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    TrendFilter,
    detect_consolidation_breakouts,
)


def _bar(
    index: int,
    *,
    close: float,
    high: float,
    low: float,
    volume: float = 100.0,
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_equivalence"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("equivalence-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _bars(
    *, breakout_close: float = 103.0, breakout_volume: float = 100.0
) -> tuple[ResearchBar, ...]:
    base = tuple(_bar(index, close=100.0, high=102.0, low=98.0, volume=100.0) for index in range(5))
    return (
        *base,
        _bar(
            5,
            close=breakout_close,
            high=max(104.0, breakout_close),
            low=101.0,
            volume=breakout_volume,
        ),
    )


def _trend_bars(trend_filter: TrendFilter) -> tuple[ResearchBar, ...]:
    history_length = 214 if trend_filter is TrendFilter.ABOVE_RISING_SMA_200 else 194
    history = tuple(
        _bar(
            index,
            close=80.0 + index * 0.1,
            high=80.5 + index * 0.1,
            low=79.5 + index * 0.1,
        )
        for index in range(history_length)
    )
    base = tuple(
        _bar(
            history_length + offset,
            close=105.0,
            high=106.0,
            low=104.0,
        )
        for offset in range(5)
    )
    signal_index = history_length + 5
    return (
        *history,
        *base,
        _bar(signal_index, close=107.0, high=108.0, low=105.0),
    )


def _assert_event_parity(
    bars: tuple[ResearchBar, ...],
    config: ConsolidationBreakoutConfig,
) -> None:
    legacy = detect_consolidation_breakouts(bars, config)
    migrated = detect_consolidation_events(bars, config)

    assert len(migrated) == len(legacy)
    assert [event.signal_index for event in migrated] == [event.signal_index for event in legacy]
    assert [event.signal_date for event in migrated] == [event.signal_date for event in legacy]
    assert [event.instrument_id for event in migrated] == [event.instrument_id for event in legacy]
    assert [event.trigger_boundary for event in migrated] == [event.boundary for event in legacy]
    assert [event.trigger_value for event in migrated] == [event.signal_close for event in legacy]
    assert [event.dataset_version for event in migrated] == [
        event.dataset_version for event in legacy
    ]


@pytest.mark.parametrize(
    ("breakout_close", "min_volume_ratio", "breakout_volume"),
    [
        (103.0, None, 100.0),
        (102.0, None, 100.0),
        (103.0, 2.0, 150.0),
        (103.0, 2.0, 250.0),
    ],
)
def test_new_pattern_event_pipeline_matches_legacy_event_semantics(
    breakout_close: float,
    min_volume_ratio: float | None,
    breakout_volume: float,
) -> None:
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
        min_breakout_volume_ratio=min_volume_ratio,
        volume_lookback_sessions=5,
    )

    _assert_event_parity(
        _bars(breakout_close=breakout_close, breakout_volume=breakout_volume),
        config,
    )


@pytest.mark.parametrize(
    "trend_filter",
    [
        TrendFilter.ABOVE_SMA_200,
        TrendFilter.ABOVE_RISING_SMA_200,
        TrendFilter.ABOVE_SMA_50_100_200,
        TrendFilter.BULLISH_SMA_STACK_50_100_200,
    ],
)
def test_new_pipeline_matches_legacy_across_supported_trend_filters(
    trend_filter: TrendFilter,
) -> None:
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=trend_filter,
        cooldown_sessions=0,
    )

    _assert_event_parity(_trend_bars(trend_filter), config)


@pytest.mark.parametrize(
    ("index", "eligibility", "quality_status"),
    [
        (2, False, QualityStatus.PASS),
        (2, True, QualityStatus.REJECT),
        (5, False, QualityStatus.PASS),
        (5, True, QualityStatus.REJECT),
    ],
)
def test_new_pipeline_matches_legacy_quality_and_eligibility_rejection(
    index: int,
    eligibility: bool,
    quality_status: QualityStatus,
) -> None:
    bars = list(_bars())
    bars[index] = replace(
        bars[index],
        eligibility=eligibility,
        quality_status=quality_status,
    )
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
    )

    _assert_event_parity(tuple(bars), config)


@pytest.mark.parametrize("breakout_close", [101.99, 102.0])
def test_new_pipeline_matches_legacy_non_breakout_boundary_cases(
    breakout_close: float,
) -> None:
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
    )

    _assert_event_parity(_bars(breakout_close=breakout_close), config)


def test_legacy_and_new_pipeline_preserve_prefix_events_when_future_bars_are_appended() -> None:
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
    )
    prefix = _bars()
    future = tuple(
        _bar(
            index,
            close=70.0 + index,
            high=75.0 + index,
            low=65.0 + index,
            volume=500.0,
        )
        for index in range(6, 12)
    )
    extended = (*prefix, *future)

    legacy_prefix = detect_consolidation_breakouts(prefix, config)
    migrated_prefix = detect_consolidation_events(prefix, config)
    legacy_extended_prefix = tuple(
        event
        for event in detect_consolidation_breakouts(extended, config)
        if event.signal_index < 6
    )
    migrated_extended_prefix = tuple(
        event for event in detect_consolidation_events(extended, config) if event.signal_index < 6
    )

    assert [event.signal_date for event in legacy_extended_prefix] == [
        event.signal_date for event in legacy_prefix
    ]
    assert [event.signal_date for event in migrated_extended_prefix] == [
        event.signal_date for event in migrated_prefix
    ]
    _assert_event_parity(prefix, config)
