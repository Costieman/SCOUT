from __future__ import annotations

from datetime import date, timedelta

from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.features.trend_context import TrendContext
from trade_scout.validation.multiplicity import MultiplicityMethod
from trade_scout.validation.trend_context_edge_family import (
    build_trend_context_edge_family_report,
)


def _series(symbol: str, *, offset: float = 0.0) -> tuple[ResearchBar, ...]:
    rows: list[ResearchBar] = []
    for index in range(520):
        base = 80.0 + offset + index * 0.08
        cycle = ((index % 30) - 15) * 0.03
        close = base + cycle
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId(f"tsi_{symbol.lower()}"),
                trade_date=date(2020, 1, 1) + timedelta(days=index),
                open=close - 0.1,
                high=close + 0.3,
                low=close - 0.3,
                close=close,
                volume=1_000_000.0,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("trend-family-test-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def _report():
    return build_trend_context_edge_family_report(
        {"AAA": _series("AAA"), "BBB": _series("BBB", offset=12.0)},
        universe_id="test",
        universe_label="Synthetic fixed cohort",
        analysis_start=date(2020, 9, 1),
        analysis_end=date(2021, 5, 20),
        horizon=20,
        sampling_stride=5,
        sma_slope_lookback=20,
        trailing_return_intervals=60,
        bootstrap_resamples=100,
        randomization_iterations=100,
        random_seed=19,
    )


def test_trend_context_family_runs_t0_through_t5_without_t6() -> None:
    report = _report()

    assert tuple(item.context for item in report.context_results) == (
        TrendContext.T0,
        TrendContext.T1,
        TrendContext.T2,
        TrendContext.T3,
        TrendContext.T4,
        TrendContext.T5,
    )
    assert report.t6_market_benchmark_status == "NOT_RUN"
    assert report.multiplicity_method is MultiplicityMethod.BENJAMINI_HOCHBERG
    assert all(item.sample_size > 0 for item in report.context_results)


def test_trend_context_family_uses_predeclared_parent_map() -> None:
    report = _report()
    parents = {item.context: item.parent_context for item in report.context_results}

    assert parents[TrendContext.T0] is None
    assert parents[TrendContext.T1] is TrendContext.T0
    assert parents[TrendContext.T2] is TrendContext.T1
    assert parents[TrendContext.T3] is TrendContext.T1
    assert parents[TrendContext.T4] is TrendContext.T3
    assert parents[TrendContext.T5] is TrendContext.T2
    for item in report.context_results[1:]:
        assert item.raw_parent_randomization_p_value is not None
        assert item.adjusted_parent_randomization_p_value is not None
        assert 0.0 <= item.raw_parent_randomization_p_value <= 1.0
        assert item.raw_parent_randomization_p_value <= item.adjusted_parent_randomization_p_value <= 1.0


def test_trend_context_family_is_deterministic_for_fixed_seed() -> None:
    first = _report()
    second = _report()

    assert first.context_results == second.context_results
    assert first.candidate_contexts == second.candidate_contexts
    assert first.verdict == second.verdict
