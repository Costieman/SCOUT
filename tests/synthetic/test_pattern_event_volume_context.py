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
from trade_scout.patterns.volume import trailing_volume_ratio


def _bar(index: int, *, close: float, high: float, low: float, volume: float) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_volume"),
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


def _bars(signal_volume: float) -> tuple[ResearchBar, ...]:
    return tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0, volume=1_000.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5, volume=signal_volume)]
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


def test_volume_gate_excludes_signal_session_from_baseline() -> None:
    bars = _bars(2_000.0)
    events = generate_close_breakout_events(
        bars,
        _states(bars),
        CloseBreakoutDefinition(
            min_breakout_volume_ratio=1.5,
            volume_lookback_sessions=10,
        ),
    )

    assert trailing_volume_ratio(bars, signal_index=10, lookback_sessions=10) == 2.0
    assert len(events) == 1
    assert any(
        item.name == "observed_breakout_volume_ratio" and item.value == "2"
        for item in events[0].resolved_parameters
    )


def test_volume_gate_fails_closed_below_threshold() -> None:
    bars = _bars(1_200.0)

    events = generate_close_breakout_events(
        bars,
        _states(bars),
        CloseBreakoutDefinition(
            min_breakout_volume_ratio=1.5,
            volume_lookback_sessions=10,
        ),
    )

    assert events == ()
