from __future__ import annotations

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


def _bars(*, breakout_close: float = 103.0, breakout_volume: float = 100.0) -> tuple[ResearchBar, ...]:
    base = tuple(
        _bar(index, close=100.0, high=102.0, low=98.0, volume=100.0)
        for index in range(5)
    )
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
    bars = _bars(breakout_close=breakout_close, breakout_volume=breakout_volume)

    legacy = detect_consolidation_breakouts(bars, config)
    migrated = detect_consolidation_events(bars, config)

    assert len(migrated) == len(legacy)
    assert [event.signal_index for event in migrated] == [event.signal_index for event in legacy]
    assert [event.signal_date for event in migrated] == [event.signal_date for event in legacy]
    assert [event.instrument_id for event in migrated] == [event.instrument_id for event in legacy]
    assert [event.trigger_boundary for event in migrated] == [event.boundary for event in legacy]
    assert [event.trigger_value for event in migrated] == [event.signal_close for event in legacy]
    assert [event.dataset_version for event in migrated] == [event.dataset_version for event in legacy]
