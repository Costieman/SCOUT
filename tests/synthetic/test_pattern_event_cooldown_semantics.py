from __future__ import annotations

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


def _bar(index: int, *, close: float, high: float, low: float) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_cooldown"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("synthetic-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def test_new_pattern_instance_can_emit_without_global_session_cooldown() -> None:
    bars = (
        _bar(0, close=100.0, high=101.0, low=99.0),
        _bar(1, close=100.0, high=101.0, low=99.0),
        _bar(2, close=102.5, high=103.0, low=102.0),
        _bar(3, close=102.5, high=103.0, low=102.0),
        _bar(4, close=104.0, high=104.5, low=103.5),
    )
    definition = ConsolidationDefinition(
        duration_sessions=2,
        max_range_pct=0.03,
        trigger_ready_distance_pct=0.02,
    )

    states = detect_consolidation_states(bars, definition)
    events = generate_close_breakout_events(bars, states)

    assert len(events) == 2
    assert events[0].signal_date == bars[2].trade_date
    assert events[1].signal_date == bars[4].trade_date
    assert events[0].pattern_instance_id != events[1].pattern_instance_id
