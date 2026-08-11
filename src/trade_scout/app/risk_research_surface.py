# ruff: noqa: E501
"""Presentation-only HTML for exploratory stop-policy comparison."""

from __future__ import annotations

from html import escape

from trade_scout.app.risk_research_service import RiskResearchReport, RiskResearchRequest
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.risk.initial_stops import StopFamily
from trade_scout.statistics.stop_research import StopPolicySummary


def render_risk_research_html(
    *,
    universes: tuple[UniverseOption, ...],
    request: RiskResearchRequest | None = None,
    report: RiskResearchReport | None = None,
    error: str | None = None,
) -> str:
    """Render the fixed-event risk research form and one already-computed comparison."""

    selected = request or RiskResearchRequest()
    universe_options = "".join(
        f'<option value="{escape(item.universe_id)}"'
        + (" selected" if item.universe_id == selected.universe_id else "")
        + f">{escape(item.label)}</option>"
        for item in universes
    )
    lookback_options = _integer_options((1, 2, 3, 5, 10, 20), selected.lookback_years, " years")
    horizon_options = _integer_options((2, 3, 5, 10, 20, 40, 60), selected.horizon, " sessions")
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
    result = _render_report(report) if report is not None else _empty_state(error)
    warning = (
        f'<div class="error"><strong>Cannot run risk research:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Risk & Stop Research</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1600px,96vw); margin:0 auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; }} h1 {{ margin:0; font-size:28px; }} h2 {{ margin:0 0 10px; font-size:18px; }} .subtle {{ color:var(--muted); }} .banner {{ border:1px solid #654f18; background:#1d1809; padding:12px 14px; border-radius:10px; margin:16px 0; }} .scope {{ border-color:#36536b; background:#0d1b26; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }}
.card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; min-width:0; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; }} .s3 {{ grid-column:span 3; }} .s4 {{ grid-column:span 4; }} .s6 {{ grid-column:span 6; }} .s12 {{ grid-column:1/-1; }} form {{ display:grid; grid-template-columns:1.5fr .7fr .8fr .8fr .9fr 1.25fr 1.3fr .8fr auto; gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} select,input,button {{ min-width:0; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} .metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }} .metric {{ font-size:24px; font-weight:760; margin-top:5px; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .warn {{ color:var(--warn); }} .blue {{ color:var(--blue); }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:5px 9px; font-size:11px; font-weight:750; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; white-space:nowrap; }} tr:last-child td {{ border-bottom:0; }} .scroll {{ overflow:auto; }} .family {{ color:var(--blue); font-size:11px; }} ul {{ padding-left:19px; }} code {{ color:#d9e3ef; }}
@media(max-width:1150px) {{ form {{ grid-template-columns:1fr 1fr; }} .s3,.s4,.s6 {{ grid-column:1/-1; }} }}
</style>
</head>
<body><div class="wrap">
<header><div><a href="/research/universe">← Universe Research</a><h1>Risk & Stop Research</h1><div class="subtle">Apply simple stop families to the same pre-defined breakout events.</div></div><span class="pill">EXPLORATORY RISK v0.1</span></header>
<div class="banner"><strong>Path first, stop second.</strong> Stops do not decide whether a breakout existed. Every policy below is tested after event detection on the same complete-horizon event population.</div>
<div class="banner scope"><strong>Execution boundary:</strong> next-session-open entry; daily low triggers an active stop; a later opening gap beyond the stop exits at that opening price before configured slippage. No target is active, so stop/target same-bar ordering is not being inferred.</div>
<div class="card">
<form action="/research/risk" method="get">
<label>Universe<select name="universe">{universe_options}</select></label>
<label>Lookback<select name="lookback_years">{lookback_options}</select></label>
<label>Horizon<select name="horizon">{horizon_options}</select></label>
<label>Base sessions<input name="duration" type="number" min="5" max="252" value="{selected.duration}"></label>
<label>Max base range %<input name="max_range_pct" type="number" min="1" max="100" step="0.5" value="{selected.max_range_pct * 100:.1f}"></label>
<label>Trend filter<select name="trend_filter">{trend_options}</select></label>
<label>Breakout volume<select name="volume_ratio">{volume_options}</select></label>
<label>Cost bps / side<input name="cost_bps" type="number" min="0" max="500" step="1" value="{selected.cost_bps_per_side:g}"></label>
<button type="submit">Compare stops</button>
</form>
</div>
{warning}
{result}
</div></body></html>"""


def _empty_state(error: str | None) -> str:
    if error:
        return ""
    return """<div class="card" style="margin-top:14px"><h2>Run Experiment H — simple stops</h2><div class="subtle">The first grid compares no stop, fixed 2/3/4/5/7/10% stops, ATR 1/1.5/2/2.5/3x stops, consolidation-low structure, breakout-boundary structure, and a boundary stop with a 0.5 ATR buffer.</div></div>"""


def _render_report(report: RiskResearchReport) -> str:
    comparison = report.comparison
    baseline = next(
        item for item in comparison.policy_summaries if item.stop_family is StopFamily.NO_STOP
    )
    warnings = "".join(f"<li>{escape(item)}</li>" for item in comparison.warnings)
    rows = "".join(_policy_row(item) for item in comparison.policy_summaries)
    return f"""
<div class="grid" style="margin-top:14px">
  <div class="card s3"><div class="metric-label">Detected events</div><div class="metric blue">{report.event_count}</div><div class="subtle">before forward-horizon completeness</div></div>
  <div class="card s3"><div class="metric-label">Common complete events</div><div class="metric">{comparison.complete_event_count}</div><div class="subtle">same sample for the policy grid</div></div>
  <div class="card s3"><div class="metric-label">No-stop expectancy</div><div class="metric {_value_class(baseline.expectancy)}">{_pct(baseline.expectancy)}</div><div class="subtle">{comparison.horizon}-session horizon</div></div>
  <div class="card s3"><div class="metric-label">Execution cost</div><div class="metric">{comparison.entry_slippage_bps:g} bp</div><div class="subtle">per side; entry and exit</div></div>

  <div class="card s6"><h2>Frozen event definition for this comparison</h2><table><tr><th>Analysis window</th><td>{report.analysis_start.isoformat()} → {report.analysis_end.isoformat()}</td></tr><tr><th>Base duration</th><td>{report.selected_config.duration} sessions</td></tr><tr><th>Maximum range</th><td>{report.selected_config.max_range_pct * 100:.1f}%</td></tr><tr><th>Trend</th><td>{escape(report.selected_config.trend_filter.value)}</td></tr><tr><th>Breakout volume</th><td>{_volume(report)}</td></tr><tr><th>Entry</th><td>Next-session open</td></tr></table></div>
  <div class="card s6"><h2>Interpretation</h2><div class="subtle">Success for the premature-stop diagnostic is fixed as: {escape(comparison.success_criterion)}. A stop that lowers loss size but repeatedly removes events that later recover can reduce expectancy. Policy selection remains exploratory and must later survive unseen and walk-forward testing.</div><ul>{warnings}</ul></div>

  <div class="card s12 scroll"><h2>Stop-distance research surface</h2><div class="subtle">Compare broad policy behavior, not the single highest expectancy row. ATR is the registered 14-session simple mean true range known at the breakout close.</div><table><thead><tr><th>Policy</th><th>n</th><th>Initial risk</th><th>Stop-out</th><th>Expectancy</th><th>Δ vs no stop</th><th>Win probability</th><th>Profit factor</th><th>Avg R</th><th>Premature stop</th><th>Gap through</th><th>Tail P05</th><th>Avg hold</th><th>Median MAE</th></tr></thead><tbody>{rows}</tbody></table></div>

  <div class="card s12"><div class="metric-label">Provenance</div><table><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Risk program</th><td><code>{escape(report.risk_program_version)}</code></td></tr><tr><th>Comparison definition</th><td><code>{escape(comparison.comparison_definition_version)}</code></td></tr><tr><th>Cost model</th><td><code>{escape(comparison.cost_model_version)}</code></td></tr><tr><th>Research state</th><td>{escape(report.research_state)}</td></tr></table></div>
</div>"""


def _policy_row(item: StopPolicySummary) -> str:
    label = _policy_label(item)
    return (
        "<tr>"
        f"<td><strong>{escape(label)}</strong><br><span class='family'>{escape(item.stop_family.value)}</span></td>"
        f"<td>{item.sample_size}</td>"
        f"<td>{_pct_unsigned(item.mean_initial_risk_pct)}</td>"
        f"<td>{_prob(item.stop_out_rate)}</td>"
        f"<td class='{_value_class(item.expectancy)}'>{_pct(item.expectancy)}</td>"
        f"<td class='{_value_class(item.expectancy_delta_vs_no_stop)}'>{_pct(item.expectancy_delta_vs_no_stop)}</td>"
        f"<td>{_prob(item.win_probability)}</td>"
        f"<td>{_num(item.profit_factor)}</td>"
        f"<td>{_num(item.average_r)}</td>"
        f"<td>{_prob(item.premature_stop_rate)}</td>"
        f"<td>{_prob(item.gap_through_frequency)}</td>"
        f"<td>{_pct(item.tail_loss_p05)}</td>"
        f"<td>{_num(item.average_holding_period_sessions)}</td>"
        f"<td>{_pct(item.median_mae_before_exit)}</td>"
        "</tr>"
    )


def _policy_label(item: StopPolicySummary) -> str:
    if item.stop_family is StopFamily.NO_STOP:
        return "No stop — hold to horizon"
    if item.stop_family is StopFamily.FIXED_PERCENT:
        return f"Fixed {item.resolved_parameters['distance_pct'] * 100:.0f}%"
    if item.stop_family is StopFamily.ATR:
        return f"ATR {item.resolved_parameters['atr_multiple']:g}x"
    if item.stop_family is StopFamily.STRUCTURAL_BASE_LOW:
        return "Structural — consolidation low"
    buffer = item.resolved_parameters.get("atr_buffer_multiple", 0.0)
    if buffer:
        return f"Structural — breakout boundary minus {buffer:g} ATR"
    return "Structural — breakout boundary"


def _volume(report: RiskResearchReport) -> str:
    value = report.selected_config.min_breakout_volume_ratio
    return "None" if value is None else f"At least {value:g}x prior 20-session average"


def _integer_options(values: tuple[int, ...], selected: int, suffix: str) -> str:
    return "".join(
        f'<option value="{value}"'
        + (" selected" if value == selected else "")
        + f">{value}{suffix}</option>"
        for value in values
    )


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _pct_unsigned(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.2f}%"


def _prob(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _value_class(value: float | None) -> str:
    if value is None:
        return "warn"
    return "good" if value > 0 else "bad" if value < 0 else ""


__all__ = ["render_risk_research_html"]
