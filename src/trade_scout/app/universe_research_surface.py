# ruff: noqa: E501
"""Presentation-only HTML for the market-wide Universe Research Analyzer."""

from __future__ import annotations

from html import escape

from trade_scout.app.universe_research_service import UniverseOption, UniverseResearchRequest
from trade_scout.statistics.universe_research import UniverseParameterCell, UniverseResearchReport


def render_universe_research_html(
    *,
    universes: tuple[UniverseOption, ...],
    request: UniverseResearchRequest | None = None,
    report: UniverseResearchReport | None = None,
    error: str | None = None,
) -> str:
    """Render the universe research form and one already-computed report."""

    selected = request or UniverseResearchRequest()
    universe_options = "".join(
        f'<option value="{escape(item.universe_id)}"'
        + (" selected" if item.universe_id == selected.universe_id else "")
        + f">{escape(item.label)}</option>"
        for item in universes
    )
    lookback_options = _options((1, 2, 3, 5, 10, 20), selected.lookback_years, " years")
    horizon_options = _options((2, 3, 5, 10, 20, 40, 60), selected.horizon, " sessions")
    trend_options = "".join(
        f'<option value="{value}"'
        + (" selected" if value == selected.trend_filter.value else "")
        + f">{label}</option>"
        for value, label in (
            ("none", "No moving-average filter"),
            ("above_sma_200", "Close above SMA 200"),
            ("above_rising_sma_200", "Close above rising SMA 200"),
            ("above_sma_50_100_200", "Close above SMA 50, 100 and 200"),
            (
                "bullish_sma_stack_50_100_200",
                "Bullish stack: close > SMA50 > SMA100 > SMA200",
            ),
        )
    )
    volume_options = "".join(
        f'<option value="{value}"'
        + (" selected" if ratio == selected.min_breakout_volume_ratio else "")
        + f">{label}</option>"
        for value, ratio, label in (
            ("none", None, "No breakout-volume gate"),
            ("1.0", 1.0, "At least 1.0x prior 20-session average"),
            ("1.25", 1.25, "At least 1.25x prior 20-session average"),
            ("1.5", 1.5, "At least 1.5x prior 20-session average"),
            ("2.0", 2.0, "At least 2.0x prior 20-session average"),
        )
    )
    warning = (
        f'<div class="error"><strong>Cannot run universe research:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    result = _render_report(report) if report is not None else _empty_state(error)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Universe Research Analyzer</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1550px,95vw); margin:0 auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:18px; }} h1 {{ margin:0; font-size:28px; }} h2 {{ margin:0 0 10px; font-size:18px; }} h3 {{ margin:0 0 8px; font-size:14px; }} .subtle {{ color:var(--muted); }}
.banner {{ border:1px solid #654f18; background:#1d1809; padding:12px 14px; border-radius:10px; margin:16px 0; }} .scope {{ border-color:#36536b; background:#0d1b26; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }}
.card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; min-width:0; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s3 {{ grid-column:span 3; }} .s4 {{ grid-column:span 4; }} .s6 {{ grid-column:span 6; }} .s8 {{ grid-column:span 8; }} .s12 {{ grid-column:1/-1; }}
form {{ display:grid; grid-template-columns:1.6fr 1.25fr .8fr .85fr .85fr 1.35fr 1.4fr auto; gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} select,input,button {{ min-width:0; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }}
.metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }} .metric {{ font-size:24px; font-weight:760; margin-top:5px; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .warn {{ color:var(--warn); }} .blue {{ color:var(--blue); }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:5px 9px; font-size:11px; font-weight:750; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} tr:last-child td {{ border-bottom:0; }} .heat td:not(:first-child) {{ text-align:center; min-width:115px; }} .pos {{ background:rgba(99,211,154,.10); }} .neg {{ background:rgba(239,123,123,.10); }} .zero {{ color:var(--muted); }} .bar {{ height:7px; background:#242d3b; border-radius:999px; overflow:hidden; margin-top:5px; }} .bar > span {{ display:block; height:100%; background:var(--accent); }}
ul {{ padding-left:19px; }} details {{ margin-top:10px; }} code {{ color:#d9e3ef; }} .scroll {{ overflow:auto; }}
@media(max-width:1150px) {{ form {{ grid-template-columns:1fr 1fr; }} .s3,.s4,.s6,.s8 {{ grid-column:1/-1; }} }}
</style>
</head>
<body><div class="wrap">
<header><div><a href="/">← Research console</a><h1>Universe Research Analyzer</h1><div class="subtle">Apply one explicit strategy across every instrument in the selected research universe.</div></div><span class="pill">EXPLORATORY RESEARCH v0.1</span></header>
<div class="banner"><strong>Research, not a signal generator.</strong> This screen is for estimating opportunity frequency, outcome distributions, breadth and parameter stability. Attractive cells remain hypotheses until holdout and robustness validation.</div>
<div class="banner scope"><strong>Current universe boundary:</strong> the first implementation uses the fully reviewed canonical equity scope available in the private workspace. It does not pretend that this is historical point-in-time S&amp;P 500 membership. A true S&amp;P 500 research universe will plug into the same interface once membership history is available.</div>
<div class="card">
<form action="/research/universe" method="get">
<label>Universe<select name="universe">{universe_options}</select></label>
<label>Strategy<select name="strategy"><option value="consolidation_breakout">Consolidation breakout</option></select></label>
<label>Lookback<select name="lookback_years">{lookback_options}</select></label>
<label>Outcome<select name="horizon">{horizon_options}</select></label>
<label>Base sessions<input name="duration" type="number" min="5" max="252" value="{selected.duration}"></label>
<label>Maximum base range %<input name="max_range_pct" type="number" min="1" max="100" step="0.5" value="{selected.max_range_pct * 100:.1f}"></label>
<label>Trend filter<select name="trend_filter">{trend_options}</select></label>
<label>Breakout volume<select name="volume_ratio">{volume_options}</select></label>
<button type="submit">Run universe research</button>
</form>
</div>
{warning}
{result}
</div></body></html>"""


def _empty_state(error: str | None) -> str:
    if error:
        return ""
    return """<div class="card" style="margin-top:14px"><h2>Define the baseline experiment</h2><div class="subtle">The analyzer will scan every available instrument, count historical setups by month, measure 2/3/5/10/20/40/60-session outcomes, compare with same-stock trend-context dates, show cross-sectional breadth and generate a nearby duration x consolidation-range surface.</div></div>"""


def _render_report(report: UniverseResearchReport) -> str:
    selected = report.selected_horizon_summary
    warnings = "".join(f"<li>{escape(item)}</li>" for item in report.warnings)
    horizon_rows = "".join(
        "<tr>"
        f"<td>{item.horizon}</td><td>{item.sample_size}</td>"
        f"<td>{_pct(item.mean_return)}</td><td>{_pct(item.median_return)}</td>"
        f"<td>{_prob(item.positive_fraction)}</td><td>{_pct(item.return_p25)}</td>"
        f"<td>{_pct(item.return_p75)}</td><td>{_pct(item.median_mfe)}</td>"
        f"<td>{_pct(item.median_mae)}</td>"
        "</tr>"
        for item in report.horizon_summaries
    )
    monthly_rows = "".join(
        f"<tr><td>{escape(item.month)}</td><td>{item.event_count}</td><td>{item.instrument_count}</td><td><div class='bar'><span style='width:{_monthly_width(report, item.event_count):.1f}%'></span></div></td></tr>"
        for item in report.monthly_hits
    )
    instrument_rows = "".join(
        "<tr>"
        f"<td><strong>{escape(item.symbol)}</strong></td><td>{item.event_count}</td>"
        f"<td>{item.complete_outcome_count}</td><td>{_pct(item.mean_return)}</td>"
        f"<td>{_pct(item.median_return)}</td><td>{_prob(item.positive_fraction)}</td>"
        "</tr>"
        for item in report.instrument_summaries[:25]
    )
    volume_gate = (
        "None"
        if report.selected_config.min_breakout_volume_ratio is None
        else f"≥ {report.selected_config.min_breakout_volume_ratio:.2f}x prior 20-session average"
    )
    return f"""
<div class="grid" style="margin-top:14px">
  <div class="card s3"><div class="metric-label">Research universe</div><div class="metric blue">{report.universe_instrument_count}</div><div class="subtle">fully reviewed instruments in this run</div></div>
  <div class="card s3"><div class="metric-label">Historical setups</div><div class="metric">{report.event_count}</div><div class="subtle">{report.mean_events_per_month:.1f}/month average · median {report.median_events_per_month:.1f}</div></div>
  <div class="card s3"><div class="metric-label">Cross-stock breadth</div><div class="metric">{_prob(report.instrument_breadth_fraction)}</div><div class="subtle">{report.instruments_with_events} instruments produced ≥1 setup</div></div>
  <div class="card s3"><div class="metric-label">Active months</div><div class="metric">{_prob(report.active_month_fraction)}</div><div class="subtle">Maximum {report.max_events_in_month} setups in one month</div></div>

  <div class="card s3"><div class="metric-label">{report.selected_horizon}-session mean</div><div class="metric {_value_class(selected.mean_return)}">{_pct(selected.mean_return)}</div><div class="subtle">n={selected.sample_size} complete outcomes</div></div>
  <div class="card s3"><div class="metric-label">Positive outcomes</div><div class="metric">{_prob(selected.positive_fraction)}</div><div class="subtle">Median return {_pct(selected.median_return)}</div></div>
  <div class="card s3"><div class="metric-label">Excess vs simple baseline</div><div class="metric {_value_class(report.excess_mean_return)}">{_pct(report.excess_mean_return)}</div><div class="subtle">Baseline {_pct(report.baseline_mean_return)} · n={report.baseline_sample_size}</div></div>
  <div class="card s3"><div class="metric-label">Event concentration</div><div class="metric">{_prob(report.top_five_event_share)}</div><div class="subtle">Share of all events from the five most active stocks</div></div>

  <div class="card s6"><h2>Baseline strategy definition</h2><table><tr><th>Strategy</th><td>Consolidation breakout</td></tr><tr><th>Signal</th><td>Daily close above the highest high in the qualified prior window</td></tr><tr><th>Entry</th><td>Next-session open</td></tr><tr><th>Analysis window</th><td>{report.analysis_start.isoformat()} → {report.analysis_end.isoformat()}</td></tr><tr><th>Base duration</th><td>{report.selected_config.duration} sessions</td></tr><tr><th>Maximum base range</th><td>{report.selected_config.max_range_pct * 100:.1f}%</td></tr><tr><th>Trend filter</th><td>{escape(report.selected_config.trend_filter.value)}</td></tr><tr><th>Breakout volume</th><td>{escape(volume_gate)}</td></tr></table></div>
  <div class="card s6"><h2>Risk/reward path evidence</h2><table><tr><th>Median MFE</th><td>{_pct(selected.median_mfe)}</td></tr><tr><th>Median MAE</th><td>{_pct(selected.median_mae)}</td></tr><tr><th>25th percentile return</th><td>{_pct(selected.return_p25)}</td></tr><tr><th>75th percentile return</th><td>{_pct(selected.return_p75)}</td></tr></table><div class="subtle" style="margin-top:10px">MFE/MAE are descriptive path measurements. ATR/volatility stop-policy experiments are intentionally a later layer so that stop selection does not redefine which breakouts existed.</div></div>

  <div class="card s12"><h2>Forward outcome profile</h2><div class="subtle">Each historical setup enters at the next session open. The table shows the same market-wide event population at several holding horizons.</div><div class="scroll"><table><thead><tr><th>Horizon</th><th>n</th><th>Mean</th><th>Median</th><th>P(return&gt;0)</th><th>P25</th><th>P75</th><th>Median MFE</th><th>Median MAE</th></tr></thead><tbody>{horizon_rows}</tbody></table></div></div>

  <div class="card s12"><h2>Where does the apparent edge live?</h2><div class="subtle">Duration x consolidation tightness under the selected moving-average and breakout-volume filters. Each cell shows excess mean return versus the same-stock trend-context baseline, complete-outcome n, contributing stocks and mean setup frequency per month. Broad stable regions matter more than isolated maxima.</div><div class="scroll">{_surface_table(report)}</div></div>

  <div class="card s6"><h2>Opportunity availability by month</h2><div class="subtle">This is the practical setup-frequency view: how many qualifying historical plays appeared across the whole research universe each month.</div><div class="scroll"><table><thead><tr><th>Month</th><th>Setups</th><th>Stocks</th><th>Relative activity</th></tr></thead><tbody>{monthly_rows}</tbody></table></div></div>
  <div class="card s6"><h2>Instrument contribution</h2><div class="subtle">Top 25 stocks by setup count. A credible market-wide effect should not depend entirely on a handful of names.</div><div class="scroll"><table><thead><tr><th>Stock</th><th>Events</th><th>Complete n</th><th>Mean</th><th>Median</th><th>P(&gt;0)</th></tr></thead><tbody>{instrument_rows}</tbody></table></div></div>

  <div class="card s8"><h2>Interpretation warnings</h2><ul>{warnings}</ul></div>
  <div class="card s4"><h2>Research state</h2><div class="metric warn">{escape(report.research_state)}</div><div class="subtle">No cell on this page is production-eligible.</div></div>
  <div class="card s12"><details><summary>Provenance and definition identity</summary><table><tr><th>Universe</th><td>{escape(report.universe_label)}</td></tr><tr><th>Universe ID</th><td><code>{escape(report.universe_id)}</code></td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Strategy version</th><td><code>{escape(report.strategy_version)}</code></td></tr><tr><th>Event definition</th><td><code>{escape(report.event_definition_version)}</code></td></tr><tr><th>Outcome definition</th><td><code>{escape(report.outcome_definition_version)}</code></td></tr><tr><th>Comparator</th><td>{escape(report.comparator_definition)}</td></tr></table></details></div>
</div>"""


def _surface_table(report: UniverseResearchReport) -> str:
    durations = tuple(sorted({item.duration for item in report.parameter_surface}))
    thresholds = tuple(sorted({item.max_range_pct for item in report.parameter_surface}))
    by_key = {(item.duration, item.max_range_pct): item for item in report.parameter_surface}
    header = "".join(f"<th>≤ {value * 100:.0f}%</th>" for value in thresholds)
    rows = []
    for duration in durations:
        cells = "".join(_surface_cell(by_key[(duration, threshold)]) for threshold in thresholds)
        rows.append(f"<tr><th>{duration} sessions</th>{cells}</tr>")
    return f'<table class="heat"><thead><tr><th>Base duration</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


def _surface_cell(cell: UniverseParameterCell) -> str:
    if cell.excess_mean_return is None:
        return '<td class="zero">—<br><span class="subtle">no complete outcomes</span></td>'
    css = "pos" if cell.excess_mean_return > 0 else "neg"
    return (
        f'<td class="{css}"><strong>{_pct(cell.excess_mean_return)}</strong>'
        f'<br><span class="subtle">n={cell.complete_outcome_count} · '
        f"{cell.instrument_count} stocks · {cell.mean_events_per_month:.1f}/mo</span></td>"
    )


def _options(values: tuple[int, ...], selected: int, suffix: str) -> str:
    return "".join(
        f'<option value="{value}"'
        + (" selected" if value == selected else "")
        + f">{value}{suffix}</option>"
        for value in values
    )


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _prob(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _value_class(value: float | None) -> str:
    if value is None:
        return "warn"
    return "good" if value > 0 else "bad" if value < 0 else ""


def _monthly_width(report: UniverseResearchReport, event_count: int) -> float:
    maximum = max((item.event_count for item in report.monthly_hits), default=0)
    if maximum <= 0:
        return 0.0
    return event_count / maximum * 100.0


__all__ = ["render_universe_research_html"]
