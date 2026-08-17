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
from trade_scout.patterns.timeframes import PatternTimeframe
from trade_scout.statistics.readable_edge import build_readable_edge_report


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
                dataset_version=DatasetVersion("readable-edge-test-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def _report():
    return build_readable_edge_report(
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
        pattern_timeframe=PatternTimeframe.DAILY,
        selected_horizon=5,
        horizons=(2, 3, 5, 10),
        bootstrap_resamples=100,
        random_iterations=100,
        random_seed=17,
    )


def test_readable_edge_reproduces_source_samples_and_adds_controls() -> None:
    report = _report()

    assert report.performance.sample_size == report.source_report.selected_horizon_summary.sample_size
    assert report.simple_baseline.sample_size == report.source_report.baseline_sample_size
    assert report.randomized_timing.matched_event_count == report.performance.sample_size
    assert 0.0 <= report.randomized_timing.one_sided_p_value <= 1.0
    assert report.performance.mean_interval is not None
    assert report.performance.mean_interval.method == "calendar-month cluster bootstrap"
    assert report.performance.win_rate_interval.lower <= report.performance.win_rate
    assert report.performance.win_rate <= report.performance.win_rate_interval.upper


def test_readable_edge_exposes_search_cost_and_validation_boundaries() -> None:
    report = _report()

    assert report.parameter_robustness.searched_cell_count == 25
    assert 0 <= report.parameter_robustness.positive_excess_cell_count <= 25
    assert tuple(item.round_trip_bps for item in report.cost_sensitivity) == (0, 5, 10, 25, 50, 100)
    assert report.cost_sensitivity[0].net_mean_return == report.performance.mean_return
    assert report.research_state == "EXPLORATORY"
    assert report.out_of_sample_status == "NOT_RUN"
    assert report.multiple_testing_status == "NOT_CORRECTED"
    assert report.portfolio_status == "NOT_RUN"


def test_readable_edge_random_control_is_deterministic_for_fixed_seed() -> None:
    first = _report()
    second = _report()

    assert first.randomized_timing == second.randomized_timing
    assert first.performance.mean_interval == second.performance.mean_interval
    assert first.simple_baseline.excess_interval == second.simple_baseline.excess_interval
