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
from trade_scout.patterns.consolidation_breakout import ConsolidationBreakoutConfig, TrendFilter
from trade_scout.statistics.consolidation_batch import build_consolidation_batch_report


def _series(symbol: str, *, count: int = 240, version: str = "test-v1") -> tuple[ResearchBar, ...]:
    start = date(2020, 1, 1)
    rows: list[ResearchBar] = []
    for index in range(count):
        close = 100.0 + index * 0.25
        rows.append(
            ResearchBar(
                instrument_id=InstrumentId(f"instrument-{symbol}"),
                trade_date=start + timedelta(days=index),
                open=close - 0.05,
                high=close + 0.10,
                low=close - 0.10,
                close=close,
                volume=1_000_000.0,
                eligibility=True,
                quality_status=QualityStatus.PASS,
                dataset_version=DatasetVersion(version),
                price_representation=PriceRepresentation.SPLIT_ADJUSTED,
            )
        )
    return tuple(rows)


def test_batch_runs_one_frozen_definition_across_symbols() -> None:
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.20,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=5,
    )

    report = build_consolidation_batch_report(
        {"AAA": _series("AAA"), "BBB": _series("BBB")},
        config=config,
        selected_horizon=5,
        horizons=(5, 10),
    )

    assert report.dataset_version == "test-v1"
    assert report.research_state == "EXPLORATORY"
    assert report.requested_symbol_count == 2
    assert report.completed_symbol_count == 2
    assert report.skipped_symbols == ()
    assert report.total_event_count > 0
    assert tuple(item.symbol for item in report.symbol_summaries) == ("AAA", "BBB")
    assert tuple(item.horizon for item in report.horizon_summaries) == (5, 10)
    assert all(item.complete_event_count > 0 for item in report.horizon_summaries)


def test_batch_skips_only_insufficient_history() -> None:
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.20,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=5,
    )

    report = build_consolidation_batch_report(
        {"FULL": _series("FULL"), "SHORT": _series("SHORT", count=20)},
        config=config,
        selected_horizon=5,
        horizons=(5,),
    )

    assert report.completed_symbol_count == 1
    assert report.skipped_symbols == ("SHORT",)


def test_batch_rejects_mixed_dataset_versions() -> None:
    config = ConsolidationBreakoutConfig(
        duration=5,
        max_range_pct=0.20,
        trend_filter=TrendFilter.NONE,
        cooldown_sessions=5,
    )

    with pytest.raises(ValueError, match="dataset versions"):
        build_consolidation_batch_report(
            {"AAA": _series("AAA", version="v1"), "BBB": _series("BBB", version="v2")},
            config=config,
            selected_horizon=5,
            horizons=(5,),
        )
