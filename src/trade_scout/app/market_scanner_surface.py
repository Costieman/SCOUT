# ruff: noqa: E501
"""Presentation-only HTML for the cross-sectional market scanner."""

from __future__ import annotations

from html import escape

from trade_scout.app.market_scanner_service import MarketScannerReport, MarketScannerRequest


def render_market_scanner_html(
    *,
    request: MarketScannerRequest | None = None,
    report: MarketScannerReport | None = None,
    error: str | None = None,
) -> str:
    selected = request or MarketScannerRequest()
    warning = (
        f'<div class="error"><strong>Cannot run scanner:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    body = _render_report(report) if report is not None else _empty_state(error)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Market Scanner</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1700px,96vw); margin:auto; padding:28px 0 70px; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} form {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} input,select,button {{ border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; }} th:first-child,td:first-child {{ text-align:left; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }} .metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }} .metric {{ font-size:24px; font-weight:760; }} @media(max-width:1000px) {{ form,.metrics {{ grid-template-columns:1fr 1fr; }} }}
</style></head><body><div class="wrap">
<a href="/">← Research console</a><h1>Market Scanner</h1><div class="subtle">Cross-sectional filtering of the latest reviewed canonical market state. Percent-return inputs use percentage points in the form below.</div>
<div class="card"><h2>Filters</h2><form action="/research/scanner" method="get">
<label>Min 20-session return %<input name="min_return_20" type="number" step="0.5" value="{_pct_input(selected.min_return_20)}"></label>
<label>Min 252-session return %<input name="min_return_252" type="number" step="1" value="{_pct_input(selected.min_return_252)}"></label>
<label>Min relative volume<input name="min_rvol" type="number" step="0.1" min="0" value="{_raw_input(selected.min_relative_volume_20)}"></label>
<label>Max realized vol %<input name="max_vol" type="number" step="1" min="0" value="{_pct_input(selected.max_realized_volatility_20)}"></label>
<label>Max ATR14 / price %<input name="max_atr" type="number" step="0.25" min="0" value="{_raw_input(selected.max_atr_pct_14)}"></label>
<label>Min distance SMA200 %<input name="min_sma200" type="number" step="1" value="{_raw_input(selected.min_distance_sma_200_pct)}"></label>
<label>Sort by<select name="sort_by">{_sort_options(selected.sort_by)}</select></label>
<label>Limit<input name="limit" type="number" min="1" max="500" value="{selected.limit}"></label>
<button type="submit">Run scanner</button>
</form></div>
<div class="card"><strong>Useful starting preset:</strong> 20-session return ≥ 5%, RVOL ≥ 1.5x, above SMA200, sorted by 20-session return. This is a descriptive screen, not a validated trading rule.</div>
{warning}{body}
</div></body></html>"""


def _empty_state(error: str | None) -> str:
    if error:
        return ""
    return '<div class="card"><h2>Ready</h2><div class="subtle">Set any combination of momentum, volume, volatility, ATR and long-term trend filters, then scan the complete reviewed canonical scope.</div></div>'


def _render_report(report: MarketScannerReport) -> str:
    rows = "".join(
        "<tr>"
        f'<td><a href="/research/market?symbol={escape(item.symbol)}&chart_sessions=120"><strong>{escape(item.symbol)}</strong></a></td>'
        f"<td>{_percent(item.return_20)}</td><td>{_percent(item.return_252)}</td>"
        f"<td>{_ratio(item.relative_volume_20)}</td><td>{_percent(item.realized_volatility_20)}</td>"
        f"<td>{_points(item.atr_pct_14)}</td><td>{_points(item.distance_sma_50_pct)}</td>"
        f"<td>{_points(item.distance_sma_200_pct)}</td><td>{escape(item.as_of)}</td></tr>"
        for item in report.rows
    )
    return f"""<div class="metrics card"><div><div class="subtle">Scanned</div><div class="metric">{report.scanned_symbol_count}</div></div><div><div class="subtle">Matched before limit</div><div class="metric">{report.matched_symbol_count}</div></div><div><div class="subtle">Unavailable for requested filters</div><div class="metric">{report.unavailable_symbol_count}</div></div></div>
<div class="card" style="overflow:auto"><h2>Results</h2><table><thead><tr><th>Symbol</th><th>20d return</th><th>252d return</th><th>RVOL</th><th>20d vol</th><th>ATR%</th><th>SMA50 dist</th><th>SMA200 dist</th><th>As of</th></tr></thead><tbody>{rows}</tbody></table></div>"""


def _pct_input(value: float | None) -> str:
    return "" if value is None else f"{value * 100:.4g}"


def _raw_input(value: float | None) -> str:
    return "" if value is None else f"{value:.4g}"


def _sort_options(selected: str) -> str:
    options = (
        ("return_20", "20-session return"),
        ("return_252", "252-session return"),
        ("relative_volume_20", "Relative volume"),
        ("realized_volatility_20", "20-session realized volatility"),
        ("atr_pct_14", "ATR14 / price"),
        ("distance_sma_200_pct", "Distance from SMA200"),
    )
    return "".join(
        f'<option value="{value}"' + (" selected" if value == selected else "") + f">{label}</option>"
        for value, label in options
    )


def _percent(value: float | None) -> str:
    if value is None:
        return "—"
    css = "good" if value >= 0 else "bad"
    return f'<span class="{css}">{value * 100:+.2f}%</span>'


def _points(value: float | None) -> str:
    if value is None:
        return "—"
    css = "good" if value >= 0 else "bad"
    return f'<span class="{css}">{value:+.2f}%</span>'


def _ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}x"


__all__ = ["render_market_scanner_html"]
