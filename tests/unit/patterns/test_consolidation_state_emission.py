from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns import PatternLifecycleState, qualified_pattern_at
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter


def _bar(index: int, *, close: float, high: float, low: float) -> ResearchBar:
    return ResearchBar(
        instrument_id=InstrumentId("tsi_test"),
        trade_date=date(2024, 1, 1) + timedelta(days=index),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=1_000_000.0,
        eligibility=True,
        quality_status=QualityStatus.PASS,
        dataset_version=DatasetVersion("dataset-v1"),
        price_representation=PriceRepresentation.SPLIT_ADJUSTED,
    )


def test_prior_window_emits_qualified_pattern_without_requiring_breakout() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=102.0, low=98.0) for index in range(5)]
        + [_bar(5, close=101.0, high=103.0, low=99.0)]
    )
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.10,
        trend_filter=TrendFilter.NONE,
    )

    state = qualified_pattern_at(bars, signal_index=5, config=config)

    assert state is not None
    assert state.state is PatternLifecycleState.QUALIFIED
    assert state.formation_end == bars[4].trade_date
    assert state.as_of_date == bars[5].trade_date
    assert state.structural_boundaries["resistance"] == 102.0
    assert state.structural_boundaries["support"] == 98.0


def test_wide_prior_window_does_not_emit_qualified_pattern() -> None:
    bars = tuple(
        [_bar(index, close=100.0, high=110.0, low=90.0) for index in range(5)]
        + [_bar(5, close=111.0, high=112.0, low=109.0)]
    )
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.10,
        trend_filter=TrendFilter.NONE,
    )

    assert qualified_pattern_at(bars, signal_index=5, config=config) is None
