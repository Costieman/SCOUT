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
from trade_scout.statistics.timeframe_universe_research import (
    build_timeframe_universe_research_report,
)


def _bars(symbol: str, *, offset: float = 0.0) -> tuple[ResearchBar, ...]:
    result: list[ResearchBar] = []
    session = date(2025, 1, 2)
    generated = 0
    while generated < 180:
        if session.weekday() < 5:
            close = 100.0 + offset + generated * 0.05
            result.append(
                ResearchBar(
                    instrument_id=InstrumentId(f"tsi_{symbol.lower()}"),
                    trade_date=session,
                    open=close - 0.1,
                    high=close + 0.3,
                    low=close - 0.3,
                    close=close,
                    volume=1_000_000.0 + generated,
                    eligibility=True,
                    quality_status=QualityStatus.PASS,
                    dataset_version=DatasetVersion("timeframe-test-v1"),
                    price_representation=PriceRepresentation.SPLIT_ADJUSTED,
                )
            )
            generated += 1
        session += timedelta(days=1)
    return tuple(result)


def test_two_session_pattern_timeframe_keeps_daily_outcome_horizon_identity() -> None:
    series = {"AAA": _bars("AAA"), "BBB": _bars("BBB", offset=5.0)}
    end = max(bars[-1].trade_date for bars in series.values())
    report = build_timeframe_universe_research_report(
        series,
        universe_id="reviewed_canonical",
        universe_label="Synthetic",
        config=ConsolidationBreakoutConfig(
            duration=5,
            max_range_pct=0.20,
            trend_filter=TrendFilter.NONE,
            cooldown_sessions=1,
        ),
        analysis_start=end - timedelta(days=180),
        analysis_end=end,
        pattern_timeframe=PatternTimeframe.TWO_SESSION,
        selected_horizon=5,
        horizons=(2, 5, 10),
        surface_durations=(5, 10),
        surface_tightness=(0.10, 0.20),
    )

    assert report.strategy_version.endswith(":2_session")
    assert report.event_definition_version == "consolidation-close-breakout-timeframe-v0.1"
    assert report.selected_horizon == 5
    assert "outcomes measured in daily trading sessions" in report.comparator_definition
    assert any("Pattern timeframe and holding horizon are separate" in item for item in report.warnings)


def test_weekly_timeframe_builds_report_without_projecting_horizon_into_weeks() -> None:
    series = {"AAA": _bars("AAA"), "BBB": _bars("BBB", offset=5.0)}
    end = max(bars[-1].trade_date for bars in series.values())
    report = build_timeframe_universe_research_report(
        series,
        universe_id="reviewed_canonical",
        universe_label="Synthetic",
        config=ConsolidationBreakoutConfig(
            duration=5,
            max_range_pct=0.25,
            trend_filter=TrendFilter.NONE,
            cooldown_sessions=1,
        ),
        analysis_start=end - timedelta(days=180),
        analysis_end=end,
        pattern_timeframe=PatternTimeframe.WEEKLY,
        selected_horizon=2,
        horizons=(2, 5),
        surface_durations=(5,),
        surface_tightness=(0.25,),
    )

    assert report.selected_horizon == 2
    assert report.strategy_version.endswith(":weekly")
    assert any("final calendar week" in item for item in report.warnings)
