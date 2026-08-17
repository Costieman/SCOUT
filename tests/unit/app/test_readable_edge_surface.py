from __future__ import annotations

from datetime import date, timedelta

from trade_scout.app.readable_edge_surface import render_readable_edge_html
from trade_scout.data.contracts import (
    DatasetVersion,
    InstrumentId,
    PriceRepresentation,
    QualityStatus,
    ResearchBar,
)
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.statistics.readable_edge import build_readable_edge_report


def _series() -> tuple[ResearchBar, ...]:
    rows: list[ResearchBar] = []
    for index in range(340):
        close = 100.0 + index * 0.05
        volume = 1_000_000.0
        if index in {240, 275, 310}:
            close += 2.5
            volume = 2_000_000.0
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId("tsi_readable_edge_surface"),
                trade_date=date(2020, 1, 1) + timedelta(days=index),
                open=close - 0.15,
                high=close + 0.35,
                low=close - 0.35,
                close=close,
                volume=volume,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion("readable-edge-surface-v1"),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def test_readable_edge_surface_exposes_edge_and_validation_boundaries() -> None:
    report = build_readable_edge_report(
        {"AAA": _series()},
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
        horizons=(5, 10),
        bootstrap_resamples=100,
        random_iterations=100,
        random_seed=23,
    )

    html = render_readable_edge_html(report, report_checksum="abc123")

    assert "Readable Edge Audit" in html
    assert report.verdict.code in html
    assert "Control 1 — current trend-context baseline" in html
    assert "Control 2 — randomized eligible timing" in html
    assert "Multiple testing" in html
    assert "NOT_CORRECTED" in html
    assert "Out of sample" in html
    assert "NOT_RUN" in html
    assert "report checksum" in html.lower()
    assert "abc123" in html
