# ruff: noqa: E501
"""Presentation-only HTML for composing reusable entry and exit families."""

from __future__ import annotations

from html import escape

from trade_scout.app.entry_strategy_registry import EntryFamily, EntryStrategyOption
from trade_scout.app.strategy_builder_service import StrategyBuilderReport, StrategyBuilderRequest
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.risk.exit_policies import ExitFamily
from trade_scout.statistics.exit_research import ExitPolicySummary


def render_strategy_builder_html(
    *,
    universes: tuple[UniverseOption, ...],
    entries: tuple[EntryStrategyOption, ...],
    features: tuple[str, ...],
    request: StrategyBuilderRequest | None = None,
    report: StrategyBuilderReport | None = None,
    error: str | None = None,
) -> str:
    """Render the first reusable strategy-builder application surface."""

    selected = request or StrategyBuilderRequest()
    universe_options = "".join(
        f'<option value="{escape(item.universe_id)}"'
        + (" selected" if item.universe_id == selected.universe_id else "")
        + f">{escape(item.label)}</option>"
        for item in universes
    )
    entry_options = "".join(
        f'<option value="{escape(item.family.value)}"'
        + (" selected" if item.family is selected.entry_family else "")
        + f">{escape(item.label)}</option>"
        for item in entries
    )
    feature_options = "".join(
        f'<option value="{escape(value)}"'
        + (" selected" if value == selected.rank_feature else "")
        + f">{escape(value)}</option>"
        for value in features
    )
    lookback_options = _integer_options((1, 2, 3, 5, 10, 20), selected.lookback_years, " years")
    horizon_options = _integer_options((2, 3, 5, 10, 20, 40, 60, 120, 252), selected.horizon, " sessions")
    direction_options = "".join(
        f'<option value="{value}"' + (" selected" if descending is selected.descending else "") + f">{label}</option>"
        for value, descending, label in (("desc", True, "Highest first"), ("asc", False, "Lowest first"))
    )
    trend_options = "".join(
        f'<option value="{value}"' + (" selected" if value == selected.trend_filter.value else "") + f">{label}</option>"
        for value, label in (
            ("none", "No moving-average filter"),
            ("above_sma_200", "Close above SMA 200"),
            ("above_rising_sma_200", "Close above rising SMA 200"),
            ("above_sma_50_100_200", "Close above SMA 50, 100 and 200"),
            ("bullish_sma_stack_50_100_200", "Bullish SMA stack"),
        )
    )
    volume_options = "".join(
        f'<option value="{value}"' + (" selected" if ratio == selected.min_breakout_volume_ratio else "") + f">{label}</option>"
        for value, ratio, label in (
            ("none", None, "No breakout-volume gate"),
            ("1.0", 1.0, "At least 1.0x prior average"),
            ("1.25", 1.25, "At least 1.25x prior average"),
            ("1.5", 1.5, "At least 1.5x prior average"),
            ("2.0", 2.0, "At least 2.0x prior average"),
        )
    )
    warning = f'<div class="error"><strong>Cannot run strategy:</strong> {escape(error)}</div>' if error else ""
    result = _render_report(report) if report is not None else _empty_state(entries, features)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout - Strategy Builder</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1780px,97vw); margin:auto; padding:28px 0 70px; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} h3 {{ margin:4px 0 10px; font-size:15px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} .banner {{ border:1px solid #36536b; background:#0d1b26; padding:12px 14px; border-radius:10px; margin-top:14px; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin-top:14px; }} form {{ display:grid; grid-template-columns:repeat(6,minmax(130px,1fr)); gap:10px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} select,input,textarea,button {{ min-width:0; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} textarea {{ min-height:76px; resize:vertical; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} .wide {{ grid-column:span 2; }} .full {{ grid-column:1/-1; }} .section {{ grid-column:1/-1; border-top:1px solid var(--border); padding-top:12px; margin-top:3px; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; margin-top:14px; }} .s3 {{ grid-column:span 3; }} .s6 {{ grid-column:span 6; }} .s12 {{ grid-column:1/-1; }} .metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} .metric {{ font-size:24px; font-weight:760; margin-top:5px; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; white-space:nowrap; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} th:first-child,td:first-child {{ text-align:left; }} .scroll {{ overflow:auto; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .blue {{ color:var(--blue); }} code {{ color:#d9e3ef; }} .chips {{ display:flex; gap:6px; flex-wrap:wrap; }} .chip {{ border:1px solid var(--border); border-radius:999px; padding:4px 8px; color:var(--blue); font-size:12px; }}
@media(max-width:1100px) {{ form {{ grid-template-columns:1fr 1fr; }} .wide {{ grid-column:span 1; }} .s3,.s6 {{ grid-column:1/-1; }} }}
@media print {{ :root {{ color-scheme:light; }} body {{ background:white; color:#111; }} .card {{ background:white; border-color:#aaa; }} .subtle,th,label {{ color:#555; }} .scroll {{ overflow:visible; }} table {{ font-size:10px; }} }}
</style></head><body><div class="wrap">
<a href="/research/exits">Exit Policy Lab</a><h1>Strategy Builder</h1><div class="subtle">Choose a setup family, configure its point-in-time rules, then apply the same reusable exit-policy engine.</div>
<div class="banner"><strong>Composition rule:</strong> entry/setup selection and exit management are independent. Changing a stop cannot change which entry events existed. Feature expressions and consolidation breakouts both emit shared event-compatible records and use the same canonical data.</div>
<div class="card"><form action="/research/strategy" method="get">
<label>Universe<select name="universe">{universe_options}</select></label>
<label>Entry family<select name="entry_family">{entry_options}</select></label>
<label>Lookback<select name="lookback_years">{lookback_options}</select></label>
<label>Research horizon<select name="horizon">{horizon_options}</select></label>
<label>Entry slip bps<input name="entry_slip" type="number" min="0" max="500" step="1" value="{selected.entry_slippage_bps:g}"></label>
<label>Exit slip bps<input name="exit_slip" type="number" min="0" max="500" step="1" value="{selected.exit_slippage_bps:g}"></label>
<div class="section"><h3>Feature-expression entry - used when Entry family = Feature expression</h3></div>
<label class="full">Entry expression<textarea name="expression">{escape(selected.expression)}</textarea></label>
<label>Rank feature<select name="rank_feature">{feature_options}</select></label>
<label>Rank direction<select name="rank_direction">{direction_options}</select></label>
<label>Max signals / session<input name="per_session_limit" type="number" min="1" max="500" value="{selected.per_session_limit}"></label>
<div class="section"><h3>Consolidation-breakout entry - used when Entry family = Consolidation breakout</h3></div>
<label>Base sessions<input name="duration" type="number" min="5" max="252" value="{selected.duration}"></label>
<label>Max base range %<input name="max_range_pct" type="number" min="0.5" max="100" step="0.5" value="{selected.max_range_pct * 100:.1f}"></label>
<label>Trend<select name="trend_filter">{trend_options}</select></label>
<label>Breakout volume<select name="volume_ratio">{volume_options}</select></label>
<div class="section"><h3>Exit-policy family - applied to whichever entry family is selected</h3></div>
<label class="wide">Fixed stop % grid<input name="fixed_stops" value="{_pct_grid(selected.fixed_percentages)}"></label>
<label class="wide">Trailing stop % grid<input name="trailing_stops" value="{_pct_grid(selected.trailing_percentages)}"></label>
<label class="wide">ATR stop grid<input name="atr_stops" value="{_num_grid(selected.atr_multiples)}"></label>
<label class="wide">Trailing ATR grid<input name="trailing_atr" value="{_num_grid(selected.trailing_atr_multiples)}"></label>
<label>Stop slip bps<input name="stop_slip" type="number" min="0" max="500" step="1" value="{selected.stop_slippage_bps:g}"></label>
<label>Commission bps/side<input name="commission" type="number" min="0" max="500" step="1" value="{selected.commission_bps_per_side:g}"></label>
<button type="submit">Run composed strategy</button>
</form></div>{warning}{result}</div></body></html>"""


def _empty_state(entries: tuple[EntryStrategyOption, ...], features: tuple[str, ...]) -> str:
    entry_cards = "".join(f"<li><strong>{escape(item.label)}</strong> - {escape(item.description)}</li>" for item in entries)
    chips = "".join(f'<span class="chip">{escape(value)}</span>' for value in features)
    return f"""<div class="grid"><div class="card s6"><h2>Registered entry families</h2><ul>{entry_cards}</ul></div><div class="card s6"><h2>Feature-expression vocabulary</h2><div class="chips">{chips}</div><p class="subtle">Expressions use only point-in-time registered features. Additions to the feature catalog automatically become available to the builder once registered.</p></div></div>"""


def _render_report(report: StrategyBuilderReport) -> str:
    comparison = report.comparison
    hold = next(item for item in comparison.policy_summaries if item.family is ExitFamily.HOLD_TO_HORIZON)
    rows = "".join(_row(item) for item in comparison.policy_summaries)
    warnings = "".join(f"<li>{escape(item)}</li>" for item in comparison.warnings)
    entry_detail = _entry_detail(report)
    return f"""<div class="grid">
<div class="card s3"><div class="metric-label">Entry family</div><div class="metric blue">{escape(report.entry_option.label)}</div></div>
<div class="card s3"><div class="metric-label">Detected entry events</div><div class="metric">{report.entry_event_count}</div></div>
<div class="card s3"><div class="metric-label">Common complete events</div><div class="metric">{comparison.complete_event_count}</div></div>
<div class="card s3"><div class="metric-label">Exit policies compared</div><div class="metric">{len(comparison.policy_summaries)}</div></div>
<div class="card s12 scroll"><h2>Composed entry + exit comparison</h2><table><thead><tr><th>Exit policy</th><th>N</th><th>Stop-out</th><th>Expectancy</th><th>Delta vs hold</th><th>Win rate</th><th>PF</th><th>Payoff</th><th>P05</th><th>Avg hold</th><th>Median hold</th><th>Median MAE</th><th>Median MFE</th><th>Median drawdown</th><th>Gap-through</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="card s6"><h2>Frozen entry definition</h2>{entry_detail}<table><tr><th>Definition version</th><td><code>{escape(report.entry_definition_version)}</code></td></tr><tr><th>Window</th><td>{report.analysis_start.isoformat()} to {report.analysis_end.isoformat()}</td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Provider calls</th><td>{str(report.provider_calls_made).lower()}</td></tr></table></div>
<div class="card s6"><h2>Interpretation boundary</h2><ul>{warnings}</ul><div class="subtle">Research state: {escape(report.research_state)}. This is a strategy-construction laboratory, not an automatic strategy-selection or production-promotion system.</div></div>
<div class="card s12"><div class="metric-label">Hold-to-horizon reference expectancy</div><div class="metric {_value_class(hold.expectancy)}">{_pct(hold.expectancy)}</div></div>
</div>"""


def _entry_detail(report: StrategyBuilderReport) -> str:
    if report.feature_strategy_report is not None:
        strategy = report.feature_strategy_report.strategy
        return f"""<table><tr><th>Expression</th><td><code>{escape(strategy.expression)}</code></td></tr><tr><th>Rank feature</th><td>{escape(strategy.rank_feature)}</td></tr><tr><th>Direction</th><td>{'highest first' if strategy.descending else 'lowest first'}</td></tr><tr><th>Per-session limit</th><td>{strategy.per_session_limit}</td></tr><tr><th>Feature set</th><td><code>{escape(report.feature_strategy_report.feature_set_version)}</code></td></tr></table>"""
    config = report.consolidation_config
    if config is None:
        return "<div class='subtle'>Entry definition unavailable.</div>"
    volume = "none" if config.min_breakout_volume_ratio is None else f"{config.min_breakout_volume_ratio:g}x"
    return f"""<table><tr><th>Duration</th><td>{config.duration} sessions</td></tr><tr><th>Max range</th><td>{config.max_range_pct * 100:.1f}%</td></tr><tr><th>Trend</th><td>{escape(config.trend_filter.value)}</td></tr><tr><th>Volume gate</th><td>{escape(volume)}</td></tr></table>"""


def _row(item: ExitPolicySummary) -> str:
    return (
        "<tr>"
        f"<td><strong>{escape(_label(item))}</strong><br><span class='blue'>{escape(item.family.value)}</span></td>"
        f"<td>{item.sample_size}</td><td>{_prob(item.stop_out_rate)}</td>"
        f"<td class='{_value_class(item.expectancy)}'>{_pct(item.expectancy)}</td>"
        f"<td class='{_value_class(item.expectancy_delta_vs_hold)}'>{_pct(item.expectancy_delta_vs_hold)}</td>"
        f"<td>{_prob(item.win_probability)}</td><td>{_num(item.profit_factor)}</td>"
        f"<td>{_num(item.payoff_ratio)}</td><td>{_pct(item.tail_loss_p05)}</td>"
        f"<td>{_num(item.average_holding_period_sessions)}</td><td>{_num(item.median_holding_period_sessions)}</td>"
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


def _integer_options(values: tuple[int, ...], selected: int, suffix: str) -> str:
    return "".join(f'<option value="{value}"' + (" selected" if value == selected else "") + f">{value}{suffix}</option>" for value in values)


def _pct_grid(values: tuple[float, ...]) -> str:
    return ",".join(f"{value * 100:g}" for value in values)


def _num_grid(values: tuple[float, ...]) -> str:
    return ",".join(f"{value:g}" for value in values)


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


__all__ = ["render_strategy_builder_html"]
