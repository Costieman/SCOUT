# ruff: noqa: E501
"""Presentation-only HTML for the Trade Scout Edge Explorer."""

from __future__ import annotations

from html import escape

from trade_scout.app.edge_explorer_service import EdgeExplorerRequest
from trade_scout.statistics.edge_explorer import EdgeExplorerReport, ParameterSurfaceCell


def render_edge_explorer_html(
    *,
    symbols: tuple[str, ...],
    request: EdgeExplorerRequest | None = None,
    report: EdgeExplorerReport | None = None,
    error: str | None = None,
) -> str:
    """Render a server-side research preview without analytical calculations."""

    selected = request or EdgeExplorerRequest(symbol=symbols[0] if symbols else "AAPL")
    options = "".join(
        f'<option value="{escape(symbol)}"' + (" selected" if symbol == selected.symbol.upper() else "") + f">{escape(symbol)}</option>"
        for symbol in symbols
    )
    horizon_options = "".join(
        f'<option value="{value}"' + (" selected" if value == selected.horizon else "") + f">{value} sessions</option>"
        for value in (5, 10, 20, 40, 60)
    )
    trend_options = "".join(
        f'<option value="{value}"' + (" selected" if value == selected.trend_filter.value else "") + f">{label}</option>"
        for value, label in (
            ("none", "No trend filter"),
            ("above_sma_200", "Price above 200-day SMA"),
            ("above_rising_sma_200", "Price above rising 200-day SMA"),
        )
    )
    result_html = _render_report(report) if report is not None else _empty_result(error)
    warning = (
        f'<div class="error"><strong>Cannot run preview:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Edge Explorer</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1500px,94vw); margin:0 auto; padding:28px 0 70px; }}
header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:18px; }} h1 {{ margin:0; font-size:27px; }} h2 {{ font-size:18px; margin:0 0 12px; }} h3 {{ font-size:14px; margin:0 0 8px; }} .subtle {{ color:var(--muted); }}
.banner {{ border:1px solid #654f18; background:#1d1809; padding:12px 14px; border-radius:10px; margin:16px 0; }}
.card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s3 {{ grid-column:span 3; }} .s4 {{ grid-column:span 4; }} .s5 {{ grid-column:span 5; }} .s7 {{ grid-column:span 7; }} .s8 {{ grid-column:span 8; }} .s12 {{ grid-column:1/-1; }}
form {{ display:grid; grid-template-columns:1.1fr 1.4fr 1fr .9fr .9fr auto; gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} select,input,button {{ border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:750; }}
.metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }} .metric {{ font-size:24px; font-weight:760; margin-top:5px; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .warn {{ color:var(--warn); }}
.pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:5px 9px; font-size:11px; font-weight:750; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} .heat td:not(:first-child) {{ text-align:center; min-width:100px; }} .pos {{ background:rgba(99,211,154,.10); }} .neg {{ background:rgba(239,123,123,.10); }} .zero {{ color:var(--muted); }}
ul {{ padding-left:19px; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }} details {{ margin-top:10px; }} code {{ color:#d9e3ef; }}
@media(max-width:1000px) {{ form {{ grid-template-columns:1fr 1fr; }} .s3,.s4,.s5,.s7,.s8 {{ grid-column:1/-1; }} }}
</style>
</head>
<body><div class="wrap">
<header><div><a href="/">← Research console</a><h1>Edge Explorer</h1><div class="subtle">Single-stock exploratory workbench for locating candidate continuation effects.</div></div><span class="pill">RESEARCH PREVIEW v0.1</span></header>
<div class="banner"><strong>Exploratory only.</strong> Positive historical results are not a recommendation or a validated strategy. Parameter searching can manufacture attractive backtests; the purpose here is to locate hypotheses for later cross-stock, out-of-sample and robustness testing.</div>
<div class="card">
<form action="/research/edge" method="get">
<label>Stock<select name="symbol">{options}</select></label>
<label>Strategy<select name="strategy"><option value="consolidation_breakout">Consolidation breakout — close above prior high</option></select></label>
<label>Outcome horizon<select name="horizon">{horizon_options}</select></label>
<label>Base duration<input name="duration" type="number" min="5" max="252" value="{selected.duration}"></label>
<label>Max range %<input name="max_range_pct" type="number" min="1" max="100" step="0.5" value="{selected.max_range_pct * 100:.1f}"></label>
<label>Trend filter<select name="trend_filter">{trend_options}</select></label>
<button type="submit">Run preview</button>
</form>
</div>
{warning}
{result_html}
</div></body></html>"""


def _empty_result(error: str | None) -> str:
    if error:
        return ""
    return '<div class="card" style="margin-top:14px"><h2>Choose a stock and run the preview</h2><div class="subtle">The workbench will show event history, forward outcomes, a same-stock trend baseline, current setup state and a nearby-parameter surface.</div></div>'


def _render_report(report: EdgeExplorerReport) -> str:
    selected = report.selected_horizon_summary
    excess_class = _value_class(report.excess_mean_return)
    warnings = "".join(f"<li>{escape(item)}</li>" for item in report.warnings)
    horizon_rows = "".join(
        "<tr>"
        f"<td>{item.horizon}</td><td>{item.sample_size}</td><td>{_pct(item.mean_return)}</td>"
        f"<td>{_pct(item.median_return)}</td><td>{_pct(item.positive_fraction)}</td>"
        f"<td>{_pct(item.return_p25)}</td><td>{_pct(item.return_p75)}</td>"
        f"<td>{_pct(item.median_mfe)}</td><td>{_pct(item.median_mae)}</td>"
        "</tr>"
        for item in report.horizon_summaries
    )
    event_dates = ", ".join(report.recent_event_dates) if report.recent_event_dates else "No qualifying events"
    return f"""
<div class="grid" style="margin-top:14px">
  <div class="card s3"><div class="metric-label">Evidence state</div><div class="metric {_state_class(report.evidence_state.value)}">{escape(report.evidence_state.value.replace('_',' '))}</div><div class="subtle">Never implies validation.</div></div>
  <div class="card s3"><div class="metric-label">Complete {report.selected_horizon}-session outcomes</div><div class="metric">{selected.sample_size}</div><div class="subtle">{report.event_count} detected events total.</div></div>
  <div class="card s3"><div class="metric-label">Mean event return</div><div class="metric {_value_class(selected.mean_return)}">{_pct(selected.mean_return)}</div><div class="subtle">Median {_pct(selected.median_return)} · positive {_pct(selected.positive_fraction)}</div></div>
  <div class="card s3"><div class="metric-label">Excess vs simple baseline</div><div class="metric {excess_class}">{_pct(report.excess_mean_return)}</div><div class="subtle">Baseline {_pct(report.baseline_mean_return)} · n={report.baseline_sample_size}</div></div>

  <div class="card s5"><h2>Current setup</h2><div class="metric-label">As of {report.current_state.as_of_date.isoformat()}</div><div class="metric">{escape(report.current_state.state.replace('_',' '))}</div><p>{escape(report.current_state.message)}</p><table><tr><th>Boundary</th><td>{_num(report.current_state.boundary)}</td></tr><tr><th>Base range</th><td>{_pct(report.current_state.base_range_pct)}</td></tr><tr><th>Distance to boundary</th><td>{_pct(report.current_state.distance_to_boundary_pct)}</td></tr><tr><th>Trend qualified</th><td>{'YES' if report.current_state.trend_qualified else 'NO'}</td></tr></table></div>
  <div class="card s7"><h2>Selected configuration</h2><table><tr><th>Strategy</th><td>Consolidation breakout</td></tr><tr><th>Signal</th><td>Daily close &gt; highest high in prior qualified window</td></tr><tr><th>Entry</th><td>Next-session open</td></tr><tr><th>Duration</th><td>{report.selected_config.duration} sessions</td></tr><tr><th>Maximum base range</th><td>{report.selected_config.max_range_pct*100:.1f}%</td></tr><tr><th>Trend filter</th><td>{escape(report.selected_config.trend_filter.value)}</td></tr><tr><th>Cooldown</th><td>{report.selected_config.cooldown_sessions} sessions</td></tr></table></div>

  <div class="card s12"><h2>Forward outcome profile</h2><div class="subtle">Returns are measured from next-session open. MFE/MAE are path measurements, not stop recommendations.</div><table><thead><tr><th>Horizon</th><th>n</th><th>Mean</th><th>Median</th><th>P(return&gt;0)</th><th>P25</th><th>P75</th><th>Median MFE</th><th>Median MAE</th></tr></thead><tbody>{horizon_rows}</tbody></table></div>

  <div class="card s12"><h2>Where does the apparent edge live?</h2><div class="subtle">Each cell is mean return minus the same-stock trend-context baseline at {report.selected_horizon} sessions. Nearby broad positive regions are more interesting than isolated maxima, but none of these cells are validation.</div>{_surface_table(report)}</div>
  <div class="card s8"><h2>Recent qualifying events</h2><div>{escape(event_dates)}</div></div>
  <div class="card s4"><h2>Warnings</h2><ul>{warnings}</ul></div>
  <div class="card s12"><details><summary>Provenance and definition identity</summary><table><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Research state</th><td>{escape(report.research_state)}</td></tr><tr><th>Strategy version</th><td><code>{escape(report.strategy_version)}</code></td></tr><tr><th>Event definition</th><td><code>{escape(report.event_definition_version)}</code></td></tr><tr><th>Outcome definition</th><td><code>{escape(report.outcome_definition_version)}</code></td></tr><tr><th>Comparator</th><td>{escape(report.comparator_definition)}</td></tr></table></details></div>
</div>"""


def _surface_table(report: EdgeExplorerReport) -> str:
    durations = tuple(sorted({item.duration for item in report.parameter_surface}))
    thresholds = tuple(sorted({item.max_range_pct for item in report.parameter_surface}))
    by_key = {(item.duration, item.max_range_pct): item for item in report.parameter_surface}
    header = "".join(f"<th>≤ {value*100:.0f}%</th>" for value in thresholds)
    rows = []
    for duration in durations:
        cells = "".join(_surface_cell(by_key[(duration, threshold)]) for threshold in thresholds)
        rows.append(f"<tr><th>{duration} sessions</th>{cells}</tr>")
    return f'<table class="heat"><thead><tr><th>Base duration</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _surface_cell(cell: ParameterSurfaceCell) -> str:
    if cell.excess_mean_return is None:
        return '<td class="zero">—<br><span class="subtle">n=0</span></td>'
    css = "pos" if cell.excess_mean_return > 0 else "neg"
    return f'<td class="{css}"><strong>{_pct(cell.excess_mean_return)}</strong><br><span class="subtle">n={cell.event_count}</span></td>'


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value*100:+.2f}%"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _value_class(value: float | None) -> str:
    if value is None:
        return "warn"
    return "good" if value > 0 else "bad" if value < 0 else ""


def _state_class(value: str) -> str:
    if "POSITIVE" in value:
        return "good"
    if "NEGATIVE" in value:
        return "bad"
    return "warn"
