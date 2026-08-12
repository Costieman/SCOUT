# ruff: noqa: E501,I001
"""Presentation-only HTML for one-symbol market analysis."""

from __future__ import annotations

from html import escape

from trade_scout.app.market_analysis_service import (
    MarketAnalysisReport,
    MarketAnalysisRequest,
)
from trade_scout.features.contracts import FeatureAvailabilityStatus


_LABELS = {
    "return_5": "5-session return",
    "return_20": "20-session return",
    "return_252": "252-session return",
    "realized_volatility_20": "20-session realized vol",
    "relative_volume_20": "Relative volume",
    "atr_pct_14": "ATR14 / price",
    "distance_sma_50_pct": "Distance from SMA50",
    "distance_sma_200_pct": "Distance from SMA200",
}


def render_market_analysis_html(
    *,
    symbols: tuple[str, ...],
    request: MarketAnalysisRequest | None = None,
    report: MarketAnalysisReport | None = None,
    error: str | None = None,
) -> str:
    selected_symbol = (
        request.symbol.upper() if request is not None else (symbols[0] if symbols else "")
    )
    chart_sessions = request.chart_sessions if request is not None else 120
    symbol_options = "".join(
        f'<option value="{escape(symbol)}"'
        + (" selected" if symbol == selected_symbol else "")
        + f">{escape(symbol)}</option>"
        for symbol in symbols
    )
    warning = (
        f'<div class="error"><strong>Cannot analyze symbol:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    body = _render_report(report) if report is not None else _empty_state(error)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Market Analysis</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1500px,96vw); margin:auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:18px; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s3 {{ grid-column:span 3; }} .s12 {{ grid-column:1/-1; }} form {{ display:grid; grid-template-columns:3fr 2fr 2fr; gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} select,button {{ border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} .metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }} .metric {{ font-size:24px; font-weight:760; margin-top:5px; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .blue {{ color:var(--blue); }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }} .chart {{ width:100%; height:260px; display:block; }} .axis {{ color:var(--muted); display:flex; justify-content:space-between; margin-top:4px; font-size:12px; }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:5px 9px; font-size:11px; font-weight:750; }}
@media(max-width:900px) {{ form {{ grid-template-columns:1fr; }} .s3 {{ grid-column:1/-1; }} }}
</style></head><body><div class="wrap">
<header><div><a href="/">← Research console</a><h1>Market Analysis</h1><div class="subtle">Point-in-time price, momentum, volatility, volume and trend context from reviewed canonical data.</div></div><span class="pill">FEATURE PACK v0.1</span></header>
<div class="card"><h2>Analyze a reviewed symbol</h2><form action="/research/market" method="get"><label>Symbol<select name="symbol">{symbol_options}</select></label><label>Chart window<select name="chart_sessions"><option value="60"{" selected" if chart_sessions == 60 else ""}>60 sessions</option><option value="120"{" selected" if chart_sessions == 120 else ""}>120 sessions</option><option value="252"{" selected" if chart_sessions == 252 else ""}>252 sessions</option></select></label><button type="submit">Analyze</button></form></div>
{warning}{body}
</div></body></html>"""


def _empty_state(error: str | None) -> str:
    if error:
        return ""
    return '<div class="card" style="margin-top:14px"><h2>Ready</h2><div class="subtle">Choose a reviewed symbol to calculate the latest market-analysis feature pack and inspect recent price context.</div></div>'


def _render_report(report: MarketAnalysisReport) -> str:
    metrics = "".join(
        _metric_card(item.feature_name, item.value, item.units, item.availability_status)
        for item in report.metrics
    )
    chart = _sparkline(report)
    first = report.price_history[0]
    last = report.price_history[-1]
    return f"""<div class="grid" style="margin-top:14px">{metrics}<div class="card s12"><div class="metric-label">Split-adjusted close · {escape(report.symbol)} · as of {report.as_of.isoformat()}</div>{chart}<div class="axis"><span>{first.trade_date.isoformat()} · {first.close:.2f}</span><span>{last.trade_date.isoformat()} · {last.close:.2f}</span></div><div class="subtle" style="margin-top:10px">Dataset: {escape(report.dataset_version)} · feature set: {escape(report.feature_set_version)}</div></div></div>"""


def _metric_card(
    name: str, value: float | None, units: str, status: FeatureAvailabilityStatus
) -> str:
    label = _LABELS.get(name, name)
    if status is not FeatureAvailabilityStatus.AVAILABLE or value is None:
        rendered = status.value
        css = "subtle"
    else:
        rendered = _format_value(value, units)
        css = _value_class(name, value)
    return f'<div class="card s3"><div class="metric-label">{escape(label)}</div><div class="metric {css}">{escape(rendered)}</div><div class="subtle">{escape(name)}</div></div>'


def _format_value(value: float, units: str) -> str:
    if units == "decimal_return":
        return f"{value * 100:+.2f}%"
    if units == "annualized_decimal_volatility":
        return f"{value * 100:.2f}%"
    if units == "percent":
        return f"{value:+.2f}%"
    if units == "ratio":
        return f"{value:.2f}x"
    return f"{value:.4f}"


def _value_class(name: str, value: float) -> str:
    if name in {
        "return_5",
        "return_20",
        "return_252",
        "distance_sma_50_pct",
        "distance_sma_200_pct",
    }:
        return "good" if value >= 0 else "bad"
    return "blue"


def _sparkline(report: MarketAnalysisReport) -> str:
    values = [item.close for item in report.price_history]
    low = min(values)
    high = max(values)
    spread = high - low
    width = 1000.0
    height = 240.0
    denominator = max(len(values) - 1, 1)
    points: list[str] = []
    for index, value in enumerate(values):
        x = index / denominator * width
        y = height / 2 if spread == 0 else height - ((value - low) / spread * height)
        points.append(f"{x:.1f},{y:.1f}")
    encoded = " ".join(points)
    return f'<svg class="chart" viewBox="0 0 1000 240" preserveAspectRatio="none" role="img" aria-label="Recent split-adjusted closing-price chart"><polyline fill="none" stroke="currentColor" stroke-width="3" vector-effect="non-scaling-stroke" points="{encoded}"/></svg>'


__all__ = ["render_market_analysis_html"]
