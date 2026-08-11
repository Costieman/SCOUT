from __future__ import annotations

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
    detect_consolidation_breakouts,
)


def _bars() -> tuple[ResearchBar, ...]:
    rows: list[ResearchBar] = []
    for index in range(230):
        close = 80.0 + index * 0.10
        volume = 1_000_000.0
        if index == 220:
            close += 3.0
            volume = 2_000_000.0
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId("tsi_filter_test"),
                trade_date=date(2024, 1, 1) + timedelta(days=index),
                open=close - 0.10,
                high=close + 0.25,
                low=close - 0.25,
                close=close,
                volume=volume,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("filter-test-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def test_breakout_can_require_close_above_all_three_moving_averages() -> None:
    events = detect_consolidation_breakouts(
        _bars(),
        ConsolidationBreakoutConfig(
            duration=20,
            max_range_pct=0.05,
            trend_filter=TrendFilter.ABOVE_SMA_50_100_200,
        ),
    )

    assert any(item.signal_index == 220 for item in events)


def test_breakout_volume_ratio_is_a_resolved_filter() -> None:
    bars = _bars()
    accepted = detect_consolidation_breakouts(
        bars,
        ConsolidationBreakoutConfig(
            duration=20,
            max_range_pct=0.05,
            trend_filter=TrendFilter.NONE,
            min_breakout_volume_ratio=1.5,
        ),
    )
    rejected = detect_consolidation_breakouts(
        bars,
        ConsolidationBreakoutConfig(
            duration=20,
            max_range_pct=0.05,
            trend_filter=TrendFilter.NONE,
            min_breakout_volume_ratio=2.5,
        ),
    )

    assert any(item.signal_index == 220 for item in accepted)
    assert all(item.signal_index != 220 for item in rejected)
