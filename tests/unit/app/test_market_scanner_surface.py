from __future__ import annotations

from trade_scout.app.market_scanner_service import (
    MarketScannerReport,
    MarketScannerRequest,
    MarketScannerRow,
)
from trade_scout.app.market_scanner_surface import render_market_scanner_html


def test_market_scanner_surface_renders_cross_section_and_links_to_analysis() -> None:
    request = MarketScannerRequest(
        min_return_20=0.05,
        min_relative_volume_20=1.5,
        min_distance_sma_200_pct=0.0,
        expression="return_20 >= 0.05 and relative_volume_20 >= 1.5",
        limit=25,
    )
    report = MarketScannerReport(
        scanned_symbol_count=65,
        matched_symbol_count=2,
        unavailable_symbol_count=1,
        request=request,
        rows=(
            MarketScannerRow(
                symbol="AAA",
                as_of="2026-08-11",
                return_20=0.12,
                return_252=0.35,
                relative_volume_20=2.1,
                realized_volatility_20=0.28,
                atr_pct_14=2.7,
                distance_sma_50_pct=8.0,
                distance_sma_200_pct=21.0,
            ),
            MarketScannerRow(
                symbol="BBB",
                as_of="2026-08-11",
                return_20=0.06,
                return_252=0.18,
                relative_volume_20=1.6,
                realized_volatility_20=0.22,
                atr_pct_14=1.9,
                distance_sma_50_pct=3.0,
                distance_sma_200_pct=9.0,
            ),
        ),
    )

    html = render_market_scanner_html(request=request, report=report)

    assert "Market Scanner" in html
    assert "65" in html
    assert "Matched before limit" in html
    assert "+12.00%" in html
    assert "2.10x" in html
    assert "Mathematical condition" in html
    assert "return_20 &gt;= 0.05 and relative_volume_20 &gt;= 1.5" in html
    assert (
        "Calls, attribute access, indexing, assignment, and arbitrary Python are rejected" in html
    )
    assert "/research/market?symbol=AAA&amp;chart_sessions=120" not in html
    assert "/research/market?symbol=AAA&chart_sessions=120" in html


def test_market_scanner_surface_has_safe_empty_state() -> None:
    html = render_market_scanner_html()

    assert "Ready" in html
    assert 'name="expression"' in html
    assert "descriptive screen, not a validated trading rule" in html
