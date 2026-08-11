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
from trade_scout.outcomes.forward_returns import measure_forward_outcomes, summarize_outcomes
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutEvent, TrendFilter


def _bar(index: int, *, open_: float, high: float, low: float, close: float) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("test-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def test_next_open_forward_path_is_hand_calculable() -> None:
    bars = (
        _bar(0, open_=99, high=101, low=98, close=100),
        _bar(1, open_=100, high=103, low=99, close=102),
        _bar(2, open_=102, high=106, low=101, close=105),
        _bar(3, open_=105, high=108, low=104, close=107),
    )
    event = ConsolidationBreakoutEvent(
        event_id="e1",
        instrument_id=InstrumentId("tsi_test"),
        signal_date=bars[0].trade_date,
        signal_index=0,
        formation_start=bars[0].trade_date,
        formation_end=bars[0].trade_date,
        boundary=100,
        signal_close=100,
        base_range_pct=0.02,
        duration=10,
        trend_filter=TrendFilter.NONE,
        dataset_version="test-v1",
    )

    outcomes = measure_forward_outcomes(bars, (event,), horizons=(2, 3))

    two = next(item for item in outcomes if item.horizon == 2)
    assert two.entry_date == bars[1].trade_date.isoformat()
    assert two.entry_price == 100
    assert two.forward_return == pytest.approx(0.05)
    assert two.mfe == pytest.approx(0.06)
    assert two.mae == pytest.approx(-0.01)

    three = next(item for item in outcomes if item.horizon == 3)
    assert three.forward_return == pytest.approx(0.07)
    assert three.mfe == pytest.approx(0.08)


def test_summary_retains_sample_size_with_distribution_metrics() -> None:
    bars = tuple(
        _bar(index, open_=100 + index, high=102 + index, low=99 + index, close=101 + index)
        for index in range(8)
    )
    events = tuple(
        ConsolidationBreakoutEvent(
            event_id=f"e{index}",
            instrument_id=InstrumentId("tsi_test"),
            signal_date=bars[index].trade_date,
            signal_index=index,
            formation_start=bars[0].trade_date,
            formation_end=bars[index].trade_date,
            boundary=100,
            signal_close=bars[index].close,
            base_range_pct=0.02,
            duration=10,
            trend_filter=TrendFilter.NONE,
            dataset_version="test-v1",
        )
        for index in (0, 2)
    )
    outcomes = measure_forward_outcomes(bars, events, horizons=(2,))

    summary = summarize_outcomes(outcomes, (2,))[0]

    assert summary.sample_size == 2
    assert summary.mean_return is not None
    assert summary.median_mfe is not None
    assert summary.median_mae is not None
