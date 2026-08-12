from __future__ import annotations

from datetime import date, timedelta

from trade_scout.app.market_analysis_service import (
    MarketAnalysisMetric,
    MarketAnalysisPricePoint,
    MarketAnalysisReport,
    MarketAnalysisRequest,
)
from trade_scout.app.market_analysis_surface import render_market_analysis_html
from trade_scout.features.contracts import FeatureAvailabilityStatus


def _report() -> MarketAnalysisReport:
    metrics = (
        MarketAnalysisMetric(
            "return_5", 0.031, "decimal_return", FeatureAvailabilityStatus.AVAILABLE
        ),
        MarketAnalysisMetric(
            "return_20", -0.012, "decimal_return", FeatureAvailabilityStatus.AVAILABLE
        ),
        MarketAnalysisMetric(
            "realized_volatility_20",
            0.245,
            "annualized_decimal_volatility",
            FeatureAvailabilityStatus.AVAILABLE,
        ),
        MarketAnalysisMetric(
            "relative_volume_20", 1.8, "ratio", FeatureAvailabilityStatus.AVAILABLE
        ),
    )
    history = tuple(
        MarketAnalysisPricePoint(date(2026, 1, 1) + timedelta(days=index), 100.0 + index)
        for index in range(30)
    )
    return MarketAnalysisReport(
        symbol="TEST",
        dataset_version="dataset-v1",
        feature_set_version="market-analysis-features-v0.1",
        as_of=history[-1].trade_date,
        metrics=metrics,
        price_history=history,
    )


def test_market_analysis_surface_renders_metrics_and_price_chart() -> None:
    html = render_market_analysis_html(
        symbols=("AAA", "TEST"),
        request=MarketAnalysisRequest(symbol="TEST", chart_sessions=120),
        report=_report(),
    )

    assert "Market Analysis" in html
    assert "TEST" in html
    assert "+3.10%" in html
    assert "-1.20%" in html
    assert "24.50%" in html
    assert "1.80x" in html
    assert "<svg" in html
    assert "dataset-v1" in html


def test_market_analysis_surface_has_safe_empty_state() -> None:
    html = render_market_analysis_html(symbols=("AAA", "BBB"))

    assert "Ready" in html
    assert "Choose a reviewed symbol" in html
