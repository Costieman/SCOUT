# ruff: noqa: E501
"""Presentation-only HTML for the configurable exit-policy laboratory."""

from __future__ import annotations

from html import escape

from trade_scout.app.exit_policy_lab_service import ExitPolicyLabReport, ExitPolicyLabRequest
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.risk.exit_policies import ExitFamily
from trade_scout.statistics.exit_research import ExitPolicySummary


def render_exit_policy_lab_html(
    *,
    universes: tuple[UniverseOption, ...],
    request: ExitPolicyLabRequest | None = None,
    report: ExitPolicyLabReport | None = None,
    error: str | None = None,
) -> str:
    """Render one configurable post-entry exit experiment."""

    selected = request or ExitPolicyLabRequest()
    universe_options = "".join(
        f'<option value="{escape(item.universe_id)}"'
        + (" selected" if item.universe_id == selected.universe_id else "")
        + f">{escape(item.label)}</option>"
        for item in universes
    )
    lookback_options = _integer_options((1, 2, 3, 5, 10, 20), selected.lookback_years, " years")
    horizon_options = _integer_options(
        (2, 3, 5, 10, 20, 40, 60, 120, 252), selected.horizon, " sessions"
    )
    trend_options = "".join(
        f'<option value="{value}"'
        + (" selected" if value == selected.trend_filter.value else "")
        + f">{label}</option>"
        for value, label in (
            ("none", "No moving-average filter"),
            ("above_sma_200", "Close above SMA 200"),
            ("above_rising_sma_200", "Close above rising SMA 200"),
            ("above_sma_50_100_200", "Close above SMA 50, 100 and 200"),
            ("bullish_sma_stack_50_100_200", "Bullish SMA stack"),
        )
    )
    volume_options = "".join(
        f'<option value="{value}"'
        + (" selected" if ratio == selected.min_breakout_volume_ratio else "")
        + f">{label}</option>"
        for value, ratio, label in (
            ("none", None, "No breakout-volume gate"),
            ("1.0", 1.0, "At least 1.0x prior average"),
            ("1.25", 1.25, "At least 1.25x prior average"),
            ("1.5", 1.5, "At least 1.5x prior average"),
            ("2.0", 2.0, "At least 2.0x prior average"),
        )
    )
    result = _render_report(report) if report is not None else _empty_state()
    warning = (
        f'<div class="error"><strong>Cannot run exit lab:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout - Exit Policy Lab</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1750px,97vw); margin:auto; padding:28px 0 70px; }} h1 {{ margin:0; font-size:29px; }} h2 {{ margin:0 0 10px; font-size:18px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} .banner {{ border:1px solid #36536b; background:#0d1b26; padding:12px 14px; border-radius:10px; margin-top:14px; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin-top:14px; }} form {{ display:grid; grid-template-columns:repeat(6,minmax(130px,1fr)); gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} select,input,button {{ min-width:0; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} .wide {{ grid-column:span 2; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; margin-top:14px; }} .s3 {{ grid-column:span 3; }} .s6 {{ grid-column:span 6; }} .s12 {{ grid-column:1/-1; }} .metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} .metric {{ font-size:24px; font-weight:760; margin-top:5px; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; white-space:nowrap; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} th:first-child,td:first-child {{ text-align:left; }} .scroll {{ overflow:auto; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .blue {{ color:var(--blue); }} code {{ color:#d9e3ef; }}
@media(max-width:1100px) {{ form {{ grid-template-columns:1fr 1fr; }} .wide {{ grid-column:span 1; }} .s3,.s6 {{ grid-column:1/-1; }} }}
</style></head><body><div class="wrap">
<a href="/research/risk">Risk & Stop Research</a><h1>Exit Policy Lab</h1><div class="subtle">Configure reusable static and dynamic exit families without changing the entry-event population.</div>
<div class="banner"><strong>Research architecture:</strong> setup/event first, exit policy second. Fixed stops, ATR stops, percentage trailing stops and ATR trailing stops are configuration data. Trailing levels ratchet only from completed prior-session information so daily OHLC bars never imply an invented intraday order.</div>
<div class="card"><form action="/research/exits" method="get">
<label>Universe<select name="universe">{universe_options}</select></label>
<label>Lookback<select name="lookback_years">{lookback_options}</select></label>
<label>Horizon<select name="horizon">{horizon_options}</select></label>
<label>Base sessions<input name="duration" type="number" min="5" max="252" value="{selected.duration}"></label>
<label>Max base range %<input name="max_range_pct" type="number" min="0.5" max="100" step="0.5" value="{selected.max_range_pct * 100:.1f}"></label>
<label>Trend<select name="trend_filter">{trend_options}</select></label>
<label>Breakout volume<select name="volume_ratio">{volume_options}</select></label>
<label class="wide">Fixed stop % grid<input name="fixed_stops" value="{_pct_grid(selected.fixed_percentages)}" placeholder="2,3,4,5,7,10"></label>
<label class="wide">Trailing stop % grid<input name="trailing_stops" value="{_pct_grid(selected.trailing_percentages)}" placeholder="2,3,5,7,10"></label>
<label class="wide">ATR stop grid<input name="atr_stops" value="{_num_grid(selected.atr_multiples)}" placeholder="1,1.5,2,2.5,3"></label>
<label class="wide">Trailing ATR grid<input name="trailing_atr" value="{_num_grid(selected.trailing_atr_multiples)}" placeholder="1,1.5,2,2.5,3"></label>
<label>Entry slip bps<input name="entry_slip" type="number" min="0" max="500" step="1" value="{selected.entry_slippage_bps:g}"></label>
<label>Exit slip bps<input name="exit_slip" type="number" min="0" max="500" step="1" value="{selected.exit_slippage_bps:g}"></label>
<label>Stop slip bps<input name="stop_slip" type="number" min="0" max="500" step="1" value="{selected.stop_slippage_bps:g}"></label>
<label>Commission bps/side<input name="commission" type="number" min="0" max="500" step="1" value="{selected.commission_bps_per_side:g}"></label>
<button type="submit">Run exit family</button>
</form></div>{warning}{result}</div></body></html>"""


def _empty_state() -> str:
    return """<div class="card"><h2>Build an exit family</h2><div class="subtle">Change any comma-separated grid above and rerun. Empty a grid to exclude that family. Hold-to-horizon is always retained as the comparison baseline.</div></div>"""


def _render_report(report: ExitPolicyLabReport) -> str:
    comparison = report.comparison
    hold = next(
        item for item in comparison.policy_summaries if item.family is ExitFamily.HOLD_TO_HORIZON
    )
    rows = "".join(_row(item) for item in comparison.policy_summaries)
    warnings = "".join(f"<li>{escape(item)}</li>" for item in comparison.warnings)
    return f"""<div class="grid">
<div class="card s3"><div class="metric-label">Detected events</div><div class="metric blue">{report.detected_event_count}</div></div>
<div class="card s3"><div class="metric-label">Common complete events</div><div class="metric">{comparison.complete_event_count}</div></div>
<div class="card s3"><div class="metric-label">Policies compared</div><div class="metric">{len(comparison.policy_summaries)}</div></div>
<div class="card s3"><div class="metric-label">Hold expectancy</div><div class="metric {_value_class(hold.expectancy)}">{_pct(hold.expectancy)}</div></div>
<div class="card s12 scroll"><h2>Exit-policy comparison</h2><table><thead><tr><th>Policy</th><th>N</th><th>Stop-out</th><th>Expectancy</th><th>Delta vs hold</th><th>Win rate</th><th>PF</th><th>Payoff</th><th>P05</th><th>Avg hold</th><th>Median hold</th><th>Median MAE</th><th>Median MFE</th><th>Median drawdown</th><th>Gap-through</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="card s6"><h2>Frozen setup harness</h2><table><tr><th>Window</th><td>{report.analysis_start.isoformat()} to {report.analysis_end.isoformat()}</td></tr><tr><th>Duration</th><td>{report.selected_config.duration}</td></tr><tr><th>Max range</th><td>{report.selected_config.max_range_pct * 100:.1f}%</td></tr><tr><th>Trend</th><td>{escape(report.selected_config.trend_filter.value)}</td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr></table></div>
<div class="card s6"><h2>Interpretation boundary</h2><ul>{warnings}</ul><div class="subtle">Research state: {escape(report.research_state)}. The exit engine is reusable; this first UI harness still uses the current consolidation-breakout event detector.</div></div>
</div>"""


def _row(item: ExitPolicySummary) -> str:
    return (
        "<tr>"
        f"<td><strong>{escape(_label(item))}</strong><br><span class='blue'>{escape(item.family.value)}</span></td>"
        f"<td>{item.sample_size}</td><td>{_prob(item.stop_out_rate)}</td>"
        f"<td class='{_value_class(item.expectancy)}'>{_pct(item.expectancy)}</td>"
        f"<td class='{_value_class(item.expectancy_delta_vs_hold)}'>{_pct(item.expectancy_delta_vs_hold)}</td>"
        f"<td>{_prob(item.win_probability)}</td><td>{_num(item.profit_factor)}</td>"
        f"<td>{_num(item.payoff_ratio)}</td><td>{_pct(item.tail_loss_p05)}</td>"
        f"<td>{_num(item.average_holding_period_sessions)}</td>"
        f"<td>{_num(item.median_holding_period_sessions)}</td>"
        f"<td>{_pct(item.median_mae_before_exit)}</td><td>{_pct(item.median_mfe_full_horizon)}</td>"
        f"<td>{_pct(item.median_max_drawdown_before_exit)}</td><td>{_prob(item.gap_through_frequency)}</td>"
        "</tr>"
    )


def _label(item: ExitPolicySummary) -> str:
    if item.family is ExitFamily.HOLD_TO_HORIZON:
        return "Hold to research horizon"
    if item.family is ExitFamily.FIXED_PERCENT_STOP:
        return f"Fixed {item.resolved_parameters['distance_pct'] * 100:g}% stop"
    if item.family is ExitFamily.TRAILING_PERCENT_STOP:
        return f"Trailing {item.resolved_parameters['distance_pct'] * 100:g}% stop"
    if item.family is ExitFamily.ATR_STOP:
        return f"ATR {item.resolved_parameters['atr_multiple']:g}x stop"
    return f"Trailing ATR {item.resolved_parameters['atr_multiple']:g}x stop"


def _pct_grid(values: tuple[float, ...]) -> str:
    return ",".join(f"{value * 100:g}" for value in values)


def _num_grid(values: tuple[float, ...]) -> str:
    return ",".join(f"{value:g}" for value in values)


def _integer_options(values: tuple[int, ...], selected: int, suffix: str) -> str:
    return "".join(
        f'<option value="{value}"'
        + (" selected" if value == selected else "")
        + f">{value}{suffix}</option>"
        for value in values
    )


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


def _prob(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _value_class(value: float | None) -> str:
    if value is None:
        return ""
    return "good" if value > 0 else "bad" if value < 0 else ""


__all__ = ["render_exit_policy_lab_html"]
