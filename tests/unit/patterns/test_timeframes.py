from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutEvent, TrendFilter
from trade_scout.patterns.timeframes import (
    PatternTimeframe,
    build_pattern_frames,
    remap_breakout_events_to_daily,
)


def _series(symbol: str, *, missing: set[int] | None = None) -> tuple[ResearchBar, ...]:
    missing = missing or set()
    instrument_id = InstrumentId(f"tsi_{symbol.lower()}")
    result: list[ResearchBar] = []
    for index in range(10):
        if index in missing:
            continue
        session = date(2026, 8, 3) + timedelta(days=index)
        if session.weekday() >= 5:
            continue
        close = 100.0 + index
        result.append(
            ResearchBar(
                instrument_id=instrument_id,
                trade_date=session,
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1000.0 + index,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("test-dataset-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(result)


def test_two_session_bars_use_shared_non_overlapping_market_blocks() -> None:
    bars = _series("AAA")
    frames = build_pattern_frames({"AAA": bars}, PatternTimeframe.TWO_SESSION)
    frame = frames["AAA"]

    assert len(frame.bars) == 4
    assert frame.source_start_indices == (0, 2, 4, 6)
    assert frame.source_end_indices == (1, 3, 5, 7)
    assert frame.bars[0].open == bars[0].open
    assert frame.bars[0].close == bars[1].close
    assert frame.bars[0].high == max(bars[0].high, bars[1].high)
    assert frame.bars[0].low == min(bars[0].low, bars[1].low)
    assert frame.bars[0].volume == bars[0].volume + bars[1].volume


def test_three_session_bars_drop_only_incomplete_trailing_block() -> None:
    bars = _series("AAA")
    frame = build_pattern_frames({"AAA": bars}, PatternTimeframe.THREE_SESSION)["AAA"]

    assert len(frame.bars) == 2
    assert frame.source_start_indices == (0, 3)
    assert frame.source_end_indices == (2, 5)


def test_missing_source_session_drops_that_instruments_whole_market_block() -> None:
    complete = _series("AAA")
    incomplete = _series("BBB", missing={1})
    frames = build_pattern_frames(
        {"AAA": complete, "BBB": incomplete},
        PatternTimeframe.TWO_SESSION,
    )

    assert len(frames["AAA"].bars) == 4
    assert len(frames["BBB"].bars) == 3
    assert frames["BBB"].bars[0].trade_date == complete[3].trade_date


def test_weekly_bars_aggregate_closed_week_and_exclude_partial_final_week() -> None:
    bars = _series("AAA")
    frame = build_pattern_frames({"AAA": bars}, PatternTimeframe.WEEKLY)["AAA"]

    assert len(frame.bars) == 1
    assert frame.source_start_indices == (0,)
    assert frame.source_end_indices == (4,)
    assert frame.bars[0].trade_date.weekday() == 4
    assert frame.bars[0].open == bars[0].open
    assert frame.bars[0].close == bars[4].close


def test_non_daily_event_maps_to_final_underlying_daily_session() -> None:
    bars = _series("AAA")
    frame = build_pattern_frames({"AAA": bars}, PatternTimeframe.TWO_SESSION)["AAA"]
    event = ConsolidationBreakoutEvent(
        event_id="event",
        instrument_id=bars[0].instrument_id,
        signal_date=frame.bars[1].trade_date,
        signal_index=1,
        formation_start=frame.bars[0].trade_date,
        formation_end=frame.bars[0].trade_date,
        boundary=101.0,
        signal_close=103.0,
        base_range_pct=0.03,
        duration=5,
        trend_filter=TrendFilter.NONE,
        dataset_version="test-dataset-v1",
    )

    remapped = remap_breakout_events_to_daily((event,), frame)[0]

    assert remapped.signal_index == 3
    assert remapped.signal_date == bars[3].trade_date
    assert remapped.event_id.endswith("pattern_timeframe=2_session")
    assert remapped.event_definition_version == "consolidation-close-breakout-timeframe-v0.1"
