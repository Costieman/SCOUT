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
from trade_scout.patterns.consolidation_breakout import (
    ConsolidationBreakoutConfig,
    TrendFilter,
    current_consolidation_state,
    detect_consolidation_breakouts,
)


def _bar(
    index: int, *, close: float, high: float | None = None, low: float | None = None
) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def test_close_breakout_uses_prior_window_only() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
        + [_bar(index, close=103.0 + index / 10) for index in range(11, 18)]
    )
    config = ConsolidationBreakoutConfig(
        duration=10,
        max_range_pct=0.03,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=5,
    )

    events = detect_consolidation_breakouts(bars, config)

    assert events[0].signal_index == 10
    assert events[0].boundary == 101.0
    assert events[0].formation_start == bars[0].trade_date
    assert events[0].formation_end == bars[9].trade_date


def test_future_changes_do_not_change_first_event() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=102.0, high=102.5, low=100.5)]
        + [_bar(index, close=103.0) for index in range(11, 30)]
    )
    config = ConsolidationBreakoutConfig(
        duration=10,
        max_range_pct=0.03,
        trend_filter=TrendFilter.NONE,
    )
    original = detect_consolidation_breakouts(bars, config)[0]
    changed = list(bars)
    changed[20:] = [
        replace(item, open=500.0, high=505.0, low=495.0, close=500.0) for item in changed[20:]
    ]

    after = detect_consolidation_breakouts(tuple(changed), config)[0]

    assert after.signal_date == original.signal_date
    assert after.boundary == original.boundary
    assert after.event_id == original.event_id


def test_current_state_reports_trigger_ready() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=101.0, low=99.0) for index in range(10)]
        + [_bar(10, close=100.5, high=100.8, low=99.8)]
    )
    state = current_consolidation_state(
        bars,
        ConsolidationBreakoutConfig(
            duration=10,
            max_range_pct=0.03,
            trend_filter=TrendFilter.NONE,
        ),
    )

    assert state.state == "TRIGGER_READY"
    assert state.boundary == 101.0
    assert state.trend_qualified is True
