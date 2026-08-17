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
from trade_scout.statistics.horizon_edge_family import build_horizon_edge_family_report
from trade_scout.validation.multiplicity import MultiplicityMethod


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
                dataset_version=DatasetVersion("horizon-family-test-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def _report():
    return build_horizon_edge_family_report(
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
        horizons=(2, 5, 10),
        bootstrap_resamples=100,
        random_iterations=100,
        random_seed=17,
    )


def test_horizon_family_applies_bh_to_complete_predeclared_family() -> None:
    report = _report()

    assert report.horizon_family == (2, 5, 10)
    assert report.multiplicity_method is MultiplicityMethod.BENJAMINI_HOCHBERG
    assert len(report.horizon_results) == 3
    for item in report.horizon_results:
        assert 0.0 <= item.randomized_timing.one_sided_p_value <= 1.0
        assert (
            item.randomized_timing.one_sided_p_value <= item.adjusted_random_timing_p_value <= 1.0
        )
        assert item.performance.sample_size > 0
        assert item.performance.mean_interval is not None


def test_horizon_family_keeps_broader_validation_boundaries_explicit() -> None:
    report = _report()

    assert report.research_state == "EXPLORATORY"
    assert report.broader_research_family_correction_status == "NOT_RUN"
    assert report.out_of_sample_status == "NOT_RUN"
    assert report.verdict.code in {
        "NO_HORIZON_CLEARS_PRELIMINARY_GATE",
        "PRELIMINARY_HORIZON_EDGE",
    }
    assert set(report.candidate_horizons).issubset(set(report.horizon_family))


def test_horizon_family_is_deterministic_for_fixed_seed() -> None:
    first = _report()
    second = _report()

    assert first.horizon_results == second.horizon_results
    assert first.candidate_horizons == second.candidate_horizons
    assert first.verdict == second.verdict
