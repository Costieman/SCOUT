from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.events.breakout import CloseBreakoutDefinition
from trade_scout.patterns.consolidation import ConsolidationDefinition, detect_consolidation_states
from trade_scout.patterns.current_projection import project_latest_pattern_state


def _bar(
    index: int, *, close: float, high: float, low: float, volume: float = 1_000.0
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_projection"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("synthetic-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def _states(bars: tuple[ResearchBar, ...]):
    return detect_consolidation_states(
        bars,
        ConsolidationDefinition(
            duration_sessions=10,
            max_range_pct=0.03,
            trigger_ready_distance_pct=0.02,
        ),
    )


def test_projection_reports_breakout_even_when_latest_structure_invalidates() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
    )
    states = _states(bars)

    projection = project_latest_pattern_state(bars, states)

    assert projection.status == "BREAKOUT"
    assert projection.trigger_boundary == 101.0
    assert projection.latest_event_id is not None
    assert projection.signal_pattern_instance_id == states[9].pattern_instance_id


def test_projection_reports_volume_gate_failure_without_erasing_structure_context() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0, volume=1_000.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5, volume=1_200.0)]
    )
    states = _states(bars)

    projection = project_latest_pattern_state(
        bars,
        states,
        CloseBreakoutDefinition(
            min_breakout_volume_ratio=1.5,
            volume_lookback_sessions=10,
        ),
    )

    assert projection.status == "VOLUME_FILTER_FAIL"
    assert projection.trigger_boundary == 101.0
    assert projection.breakout_volume_ratio == 1.2
    assert projection.latest_event_id is None
