from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events import ConsolidationEventConfig, detect_consolidation_events
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter


def _bar(index: int, *, close: float, high: float, low: float, volume: float = 100.0) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _bars(*, breakout_volume: float = 100.0) -> tuple[ResearchBar, ...]:
    base = tuple(_bar(index, close=100.0, high=102.0, low=98.0) for index in range(5))
    return (*base, _bar(5, close=103.0, high=104.0, low=101.0, volume=breakout_volume))


def _pattern_config() -> ConsolidationBreakoutConfig:
    return ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.05,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=0,
    )


def test_batch_pipeline_emits_event_from_pattern_state() -> None:
    events = detect_consolidation_events(_bars(), _pattern_config())

    assert len(events) == 1
    assert events[0].signal_index == 5
    assert events[0].trigger_boundary == 102.0
    assert events[0].trigger_value == 103.0
    assert events[0].pattern_instance_id


def test_event_side_volume_confirmation_can_block_breakout() -> None:
    event_config = ConsolidationEventConfig(
        cooldown_sessions=0,
        min_breakout_volume_ratio=2.0,
        volume_lookback_sessions=5,
    )

    assert detect_consolidation_events(
        _bars(breakout_volume=150.0),
        _pattern_config(),
        event_config=event_config,
    ) == ()

    events = detect_consolidation_events(
        _bars(breakout_volume=250.0),
        _pattern_config(),
        event_config=event_config,
    )
    assert len(events) == 1
