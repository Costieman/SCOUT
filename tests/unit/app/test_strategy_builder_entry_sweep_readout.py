from __future__ import annotations

from datetime import date

from trade_scout.app.strategy_builder_entry_sweep import (
    EntrySweepParameter,
    EntrySweepPoint,
    StrategyBuilderEntrySweepReport,
)
from trade_scout.app.strategy_builder_entry_sweep_chart import render_entry_sweep_chart
from trade_scout.app.strategy_builder_entry_sweep_surface import attach_entry_sweep_html


def _report() -> StrategyBuilderEntrySweepReport:
    values = (150.0, 175.0, 200.0, 225.0, 250.0)
    expectancies = (0.0114, 0.0103, 0.0098, 0.0095, 0.0104)
    complete = (2488, 2277, 2041, 1912, 1895)
    entry = (2631, 2403, 2152, 2009, 1988)
    points = tuple(
        EntrySweepPoint(
            value=value,
            resolved_feature_name=f"pi__moving_average__ma_distance_pct__close__p{int(value)}__sma",
            entry_event_count=entry[index],
            complete_event_count=complete[index],
            expectancy=expectancies[index],
            win_probability=0.53,
            profit_factor=1.34,
            tail_loss_p05=-0.135,
            average_holding_period_sessions=20.0,
        )
        for index, value in enumerate(values)
    )
    return StrategyBuilderEntrySweepReport(
        target_feature_name="pi__moving_average__ma_distance_pct__close__p200__sma",
        parameter=EntrySweepParameter.PERIOD,
        parameter_label="Moving Average period",
        unit_label="trading days",
        values=values,
        points=points,
        dataset_version="synthetic-v1",
        analysis_start=date(2024, 8, 7),
        analysis_end=date(2026, 8, 7),
        search_space_fingerprint="a" * 64,
        total_seconds=76.49,
    )


def test_entry_sweep_readout_describes_shape_without_claiming_optimum() -> None:
    html = attach_entry_sweep_html("<div></div></body></html>", _report())

    assert "What this run says" in html
    assert "0.19 percentage points" in html
    assert "Every tested cell had positive historical hold expectancy" in html
    assert "edge of the declared range" in html
    assert "does not identify an interior sweet spot" in html
    assert "No uncertainty adjustment, matched comparator, or out-of-sample validation" in html


def test_entry_sweep_readout_explicitly_says_stops_are_not_applied() -> None:
    html = attach_entry_sweep_html("<div></div></body></html>", _report())

    assert "Exit policies applied in this sweep:</strong> none" in html
    assert "configured stop rows shown above are preserved for later experiments" in html
    assert "maximum holding period as its forced exit" in html


def test_entry_sweep_chart_labels_every_declared_point_and_is_print_aware() -> None:
    chart = render_entry_sweep_chart(_report())
    html = attach_entry_sweep_html("<div></div></body></html>", _report())

    for value in ("150", "175", "200", "225", "250"):
        assert f">{value}</text>" in chart
    assert "+1.14%" in chart
    assert "entry-sweep-grid" in chart
    assert "@media print" in html
