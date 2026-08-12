from __future__ import annotations

from trade_scout.app.historical_strategy_research_service import HistoricalStrategyResearchReport
from trade_scout.app.historical_strategy_research_surface import (
    render_historical_strategy_research_html,
)
from trade_scout.app.strategy_definition import MOMENTUM_RVOL_TREND
from trade_scout.app.strategy_outcome_service import StrategyHorizonSummary


def test_strategy_research_surface_renders_named_strategy_and_empty_state() -> None:
    html = render_historical_strategy_research_html(
        selected_strategy_id=MOMENTUM_RVOL_TREND.strategy_id
    )

    assert "Historical Strategy Research" in html
    assert MOMENTUM_RVOL_TREND.name in html
    assert MOMENTUM_RVOL_TREND.expression in html
    assert "descriptive research, not a portfolio backtest" in html


def test_strategy_research_surface_renders_horizon_summary() -> None:
    report = HistoricalStrategyResearchReport(
        strategy=MOMENTUM_RVOL_TREND,
        horizons=(5,),
        instrument_count=42,
        signal_count=17,
        signals=(),
        outcomes=(),
        summaries=(
            StrategyHorizonSummary(
                horizon=5,
                sample_size=12,
                mean_return=0.02,
                median_return=0.015,
                positive_fraction=0.75,
                median_mfe=0.04,
                median_mae=-0.01,
                median_max_drawdown=-0.02,
            ),
        ),
    )

    html = render_historical_strategy_research_html(
        selected_strategy_id=MOMENTUM_RVOL_TREND.strategy_id,
        report=report,
    )

    assert "42" in html
    assert "17" in html
    assert "12" in html
    assert "+2.00%" in html
    assert "75.0%" in html
