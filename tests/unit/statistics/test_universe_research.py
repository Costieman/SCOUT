from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.statistics.universe_research import build_universe_research_report


def _series(symbol: str, *, price_offset: float = 0.0) -> tuple[ResearchBar, ...]:
    rows: list[ResearchBar] = []
    breakout_indices = {240, 275, 310}
    for index in range(340):
        close = 100.0 + price_offset + index * 0.05
        volume = 1_000_000.0
        if index in breakout_indices:
            close += 2.5
            volume = 2_000_000.0
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId(f"tsi_{symbol.lower()}"),
                trade_date=date(2020, 1, 1) + timedelta(days=index),
                open=close - 0.15,
                high=close + 0.35,
                low=close - 0.35,
                close=close,
                volume=volume,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("universe-test-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def test_universe_report_counts_breadth_frequency_and_parameter_surface() -> None:
    report = build_universe_research_report(
        {"AAA": _series("AAA"), "BBB": _series("BBB", price_offset=10.0)},
        universe_id="test",
        universe_label="Synthetic test universe",
        config=ConsolidationBreakoutConfig(
            duration=20,
            max_range_pct=0.05,
            trend_filter=TrendFilter.NONE,
            min_breakout_volume_ratio=1.5,
        ),
        analysis_start=date(2020, 7, 1),
        analysis_end=date(2020, 12, 5),
        selected_horizon=5,
        horizons=(2, 3, 5, 10),
    )

    assert report.dataset_version == "universe-test-v1"
    assert report.universe_instrument_count == 2
    assert report.event_count >= 4
    assert report.instruments_with_events == 2
    assert report.instrument_breadth_fraction == 1.0
    assert report.selected_horizon_summary.sample_size > 0
    assert len(report.parameter_surface) == 25
    assert len(report.monthly_hits) == 6
    assert report.mean_events_per_month > 0
    assert report.research_state == "EXPLORATORY"


def test_universe_report_retains_zero_event_months() -> None:
    report = build_universe_research_report(
        {"AAA": _series("AAA")},
        universe_id="test",
        universe_label="Synthetic test universe",
        config=ConsolidationBreakoutConfig(
            duration=20,
            max_range_pct=0.05,
            trend_filter=TrendFilter.NONE,
            min_breakout_volume_ratio=1.5,
        ),
        analysis_start=date(2020, 1, 1),
        analysis_end=date(2020, 12, 5),
        selected_horizon=5,
        horizons=(5,),
    )

    assert len(report.monthly_hits) == 12
    assert any(item.event_count == 0 for item in report.monthly_hits)
