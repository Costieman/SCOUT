# ruff: noqa: E501
# fmt: off
"""Presentation-only HTML for visually composing reusable entry and exit families."""

from __future__ import annotations

import json
from html import escape
from urllib.parse import urlencode

from trade_scout.app.entry_strategy_registry import EntryStrategyOption
from trade_scout.app.strategy_builder_service import StrategyBuilderReport, StrategyBuilderRequest
from trade_scout.app.strategy_indicator_catalog import indicator_catalog_json_ready
from trade_scout.app.strategy_presets import StrategyPreset, available_strategy_presets
from trade_scout.app.universe_research_service import UniverseOption
from trade_scout.app.visual_rule_builder import recover_visual_conditions
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
    """Render the interactive visual Strategy Builder application surface."""

    selected = request or StrategyBuilderRequest()
    universe_options = "".join(
        f'<option value="{escape(item.universe_id)}"' + (" selected" if item.universe_id == selected.universe_id else "") + f">{escape(item.label)}</option>"
        for item in universes
    )
    rank_options = "".join(
        f'<option value="{escape(value)}"' + (" selected" if value == selected.rank_feature else "") + f">{escape(_rank_label(value))}</option>"
        for value in features
    )
    lookback_options = _integer_options((1, 2, 3, 5, 10, 20), selected.lookback_years, " years")
    horizon_options = _integer_options((2, 3, 5, 10, 20, 40, 60, 120, 252), selected.horizon, " trading days")
    direction_options = "".join(
        f'<option value="{value}"' + (" selected" if descending is selected.descending else "") + f">{label}</option>"
        for value, descending, label in (("desc", True, "Highest first"), ("asc", False, "Lowest first"))
    )
    warning = f'<div class="error"><strong>Cannot run strategy:</strong> {escape(error)}</div>' if error else ""
    result = _render_report(report) if report is not None else _empty_state(entries)
    recovered_conditions = selected.visual_conditions or recover_visual_conditions(selected.expression)
    initial_rules = [
        {
            "feature_name": item.feature_name,
            "operator": item.operator.value,
            "value": item.value,
            "join": item.join.value,
        }
        for item in recovered_conditions
    ]
    initial_stops = _initial_stops(selected, use_defaults=request is not None)
    catalog_json = escape(json.dumps(indicator_catalog_json_ready(), separators=(",", ":")))
    rules_json = escape(json.dumps(initial_rules, separators=(",", ":")))
    stops_json = escape(json.dumps(initial_stops, separators=(",", ":")))
    examples = "".join(_example_link(item, selected) for item in available_strategy_presets())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout - Visual Strategy Builder</title>
<script src="/assets/strategy-builder.js" defer></script>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1800px,97vw); margin:auto; padding:26px 0 70px; }} h1 {{ margin:2px 0 0; font-size:31px; }} h2 {{ margin:0 0 8px; font-size:19px; }} h3 {{ margin:0 0 7px; font-size:15px; }} .subtle {{ color:var(--muted); }} .eyebrow {{ color:var(--accent); font-size:11px; text-transform:uppercase; letter-spacing:.12em; font-weight:750; }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:12px; padding:16px; margin-top:14px; }} .banner {{ border:1px solid #36536b; background:#0d1b26; padding:12px 14px; border-radius:10px; margin-top:14px; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin-top:14px; }} .top-grid {{ display:grid; grid-template-columns:repeat(6,minmax(130px,1fr)); gap:10px; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} select,input,textarea,button {{ min-width:0; border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:9px 10px; font:inherit; }} input[type=range] {{ padding:0; border:0; }} textarea {{ min-height:92px; resize:vertical; }} button,.run-link {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} .primary {{ padding:12px 18px; font-size:15px; }} .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-top:10px; }} .composer-row {{ display:grid; grid-template-columns:100px 1.15fr 1.45fr 135px 140px 1.35fr 90px; gap:8px; align-items:end; padding:11px; border:1px solid var(--border); border-radius:10px; background:var(--panel2); margin-top:8px; }} .composer-row .rule-meta {{ grid-column:2/-1; color:var(--muted); font-size:12px; }} .threshold-unit {{ grid-column:2/-1; color:var(--blue); font-size:12px; }} .indicator-parameters {{ display:grid; grid-template-columns:repeat(4,minmax(160px,1fr)); gap:9px; align-items:end; padding-top:8px; }} .parameter-pair {{ display:grid; grid-template-columns:115px 1fr; gap:8px; align-items:center; }} .quick-periods {{ display:flex; gap:5px; margin-top:4px; }} .quick-periods button {{ padding:4px 8px; font-size:11px; }} .parameter-note {{ align-self:center; color:var(--muted); font-size:12px; padding:8px 0; }} .stop-row {{ grid-template-columns:1.2fr 150px 1.5fr 1fr 90px; }} .stop-unit {{ align-self:center; color:var(--muted); font-size:12px; padding-bottom:9px; }} .remove-row {{ background:#211416; color:#efb0b0; border-color:#553033; }} .mode-row {{ display:flex; gap:16px; align-items:center; margin:8px 0 10px; }} .mode-row label {{ display:flex; flex-direction:row; align-items:center; gap:7px; text-transform:none; letter-spacing:0; font-size:13px; }} .mode-row input {{ width:auto; }} .section-note {{ padding:9px 11px; background:#10151d; border-left:3px solid #426481; color:var(--muted); margin:9px 0; }} details {{ margin-top:14px; }} summary {{ cursor:pointer; color:var(--accent); font-weight:700; }} .examples {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:8px; margin-top:10px; }} .example {{ border:1px solid var(--border); border-radius:9px; padding:10px; background:var(--panel2); }} .example code {{ display:block; white-space:normal; color:#cfd8e5; margin:6px 0; }} .grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; margin-top:14px; }} .s3 {{ grid-column:span 3; }} .s6 {{ grid-column:span 6; }} .s12 {{ grid-column:1/-1; }} .metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} .metric {{ font-size:24px; font-weight:760; margin-top:5px; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; white-space:nowrap; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} th:first-child,td:first-child {{ text-align:left; }} .scroll {{ overflow:auto; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .blue {{ color:var(--blue); }} code {{ color:#d9e3ef; }}
@media(max-width:1200px) {{ .top-grid {{ grid-template-columns:1fr 1fr; }} .composer-row,.stop-row {{ grid-template-columns:1fr 1fr; }} .composer-row .rule-meta,.threshold-unit {{ grid-column:1/-1; }} .indicator-parameters {{ grid-template-columns:1fr 1fr; }} .examples {{ grid-template-columns:1fr; }} .s3,.s6 {{ grid-column:1/-1; }} }}
@media print {{ :root {{ color-scheme:light; }} body {{ background:white; color:#111; }} .card,.composer-row,.example {{ background:white; border-color:#aaa; }} .subtle,th,label,.rule-meta,.stop-unit {{ color:#555; }} .scroll {{ overflow:visible; }} table {{ font-size:10px; }} }}
</style></head><body><div class="wrap">
<div class="eyebrow">Trade Scout research laboratory</div><h1>Visual Strategy Builder</h1><div class="subtle">Build entry rules with familiar technical indicators, then compare exit policies on the same frozen entry population.</div>
<div class="banner"><strong>Terminology:</strong> all indicator periods are daily trading days in this version. Indicator period describes the signal; outcome horizon describes how long SCOUT measures the trade after the signal. Percentage fields are shown as percentages, not internal decimal returns.</div>
<form id="strategy-form" action="/research/strategy" method="get">
<input type="hidden" name="entry_family" value="feature_expression">
<div class="card"><h2>1. Research scope</h2><div class="top-grid">
<label>Universe<select name="universe">{universe_options}</select></label>
<label>Historical lookback<select name="lookback_years">{lookback_options}</select></label>
<label>Outcome horizon<select name="horizon">{horizon_options}</select></label>
<label>Ranking metric (only matters if capped)<select name="rank_feature">{rank_options}</select></label>
<label>Ranking direction<select name="rank_direction">{direction_options}</select></label>
<label>Max qualifying signals / day<input name="per_session_limit" type="number" min="1" max="500" value="{selected.per_session_limit}"></label>
</div><div class="section-note">Ranking does not create an entry signal. It only decides which qualifying stocks are retained when more signals occur on one day than the cap allows.</div></div>
<div class="card"><h2>2. Entry conditions</h2><div class="mode-row"><label><input id="entry-mode-visual" type="radio" name="ui_entry_mode" value="visual" checked> Visual builder</label><label><input id="entry-mode-advanced" type="radio" name="ui_entry_mode" value="advanced"> Advanced expression</label></div>
<div id="visual-builder-panel"><div class="section-note">Choose an industry-standard indicator, set its period and parameters, then choose the condition. Use + Add condition to combine rules with AND or OR.</div><div id="rule-rows"></div><div class="toolbar"><button id="add-rule" type="button">+ Add condition</button></div></div>
<div id="advanced-builder-panel" hidden><label>Advanced safe expression<textarea id="advanced-expression">{escape(selected.expression)}</textarea></label><div class="section-note">Advanced mode preserves exact internal feature expressions for reproducibility. Normal strategy design should use the visual controls.</div></div>
</div>
<div class="card"><h2>3. Exit candidates to compare</h2><div class="section-note">Hold-to-horizon is always the control. Add any fixed, trailing, ATR, or trailing-ATR stops you want to compare against it. Percentage stops accept exact values from 0.01% to 99.99%.</div><div id="stop-rows"></div><div class="toolbar"><button id="add-stop" type="button">+ Add exit candidate</button><button id="clear-stops" type="button">Clear all stops</button><span class="subtle">Hold-to-horizon remains even when no stop rows are present.</span></div></div>
<div class="card"><h2>4. Execution assumptions</h2><div class="top-grid"><label>Entry slippage bps<input name="entry_slip" type="number" min="0" max="500" step="0.1" value="{selected.entry_slippage_bps:g}"></label><label>Normal exit slippage bps<input name="exit_slip" type="number" min="0" max="500" step="0.1" value="{selected.exit_slippage_bps:g}"></label><label>Stop slippage bps<input name="stop_slip" type="number" min="0" max="500" step="0.1" value="{selected.stop_slippage_bps:g}"></label><label>Commission bps / side<input name="commission" type="number" min="0" max="500" step="0.1" value="{selected.commission_bps_per_side:g}"></label></div><div class="toolbar"><button class="primary" type="submit">Run research</button></div></div>
</form>
<div id="composer-error" class="error" hidden></div>{warning}
<textarea id="strategy-catalog-json" hidden>{catalog_json}</textarea><textarea id="initial-rules-json" hidden>{rules_json}</textarea><textarea id="initial-stops-json" hidden>{stops_json}</textarea>
<details class="card"><summary>Load an example hypothesis</summary><div class="subtle">Examples only pre-fill controls. They are not a privileged list of strategies.</div><div class="examples">{examples}</div></details>
{result}</div></body></html>"""


def _initial_stops(selected: StrategyBuilderRequest, *, use_defaults: bool) -> list[dict[str, object]]:
    if not use_defaults:
        return [
            {"family": "fixed", "value": 2.0},
            {"family": "fixed", "value": 5.0},
            {"family": "trailing", "value": 5.0},
            {"family": "atr", "value": 2.0},
        ]
    rows: list[dict[str, object]] = []
    rows.extend({"family": "fixed", "value": value * 100.0} for value in selected.fixed_percentages)
    rows.extend({"family": "trailing", "value": value * 100.0} for value in selected.trailing_percentages)
    rows.extend({"family": "atr", "value": value} for value in selected.atr_multiples)
    rows.extend({"family": "trailing_atr", "value": value} for value in selected.trailing_atr_multiples)
    return rows


def _example_link(preset: StrategyPreset, selected: StrategyBuilderRequest) -> str:
    query = urlencode({
        "universe": selected.universe_id,
        "entry_family": "feature_expression",
        "lookback_years": selected.lookback_years,
        "horizon": selected.horizon,
        "expression": preset.expression,
        "rank_feature": preset.rank_feature,
        "rank_direction": "desc" if preset.descending else "asc",
        "per_session_limit": preset.per_session_limit,
    })
    return f"""<div class="example"><strong>{escape(preset.label)}</strong><div class="subtle">{escape(preset.description)}</div><code>{escape(preset.expression)}</code><a class="run-link" href="/research/strategy?{escape(query)}">Load / run example</a></div>"""


def _empty_state(entries: tuple[EntryStrategyOption, ...]) -> str:
    entry_text = ", ".join(item.label for item in entries)
    return f"""<div class="card"><h2>Metric definitions</h2><p>The primary visual builder now uses configurable industry-standard indicators rather than fixed 5/20/252-day variants. Periods and thresholds are set directly in each condition. Existing registered entry engines remain underneath ({escape(entry_text)}); the UI does not create a second backtester.</p></div>"""


def _render_report(report: StrategyBuilderReport) -> str:
    comparison = report.comparison
    hold = next(item for item in comparison.policy_summaries if item.family is ExitFamily.HOLD_TO_HORIZON)
    rows = "".join(_row(item) for item in comparison.policy_summaries)
    warnings = "".join(f"<li>{escape(item)}</li>" for item in comparison.warnings)
    return f"""<div class="grid">
<div class="card s3"><div class="metric-label">Entry events</div><div class="metric">{report.entry_event_count}</div></div>
<div class="card s3"><div class="metric-label">Common complete events</div><div class="metric">{comparison.complete_event_count}</div></div>
<div class="card s3"><div class="metric-label">Exit candidates + hold</div><div class="metric">{len(comparison.policy_summaries)}</div></div>
<div class="card s3"><div class="metric-label">Hold expectancy</div><div class="metric {_value_class(hold.expectancy)}">{_pct(hold.expectancy)}</div></div>
<div class="card s12 scroll"><h2>Exit comparison on frozen entry population</h2><table><thead><tr><th>Exit policy</th><th>N</th><th>Stop-out</th><th>Expectancy</th><th>Delta vs hold</th><th>Win rate</th><th>PF</th><th>Payoff</th><th>P05</th><th>Avg hold</th><th>Median hold</th><th>Median MAE</th><th>Median MFE</th><th>Median drawdown</th><th>Gap-through</th></tr></thead><tbody>{rows}</tbody></table></div>
<div class="card s6"><h2>Frozen entry definition</h2>{_entry_detail(report)}<table><tr><th>Definition version</th><td><code>{escape(report.entry_definition_version)}</code></td></tr><tr><th>Window</th><td>{report.analysis_start.isoformat()} to {report.analysis_end.isoformat()}</td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Provider calls</th><td>{str(report.provider_calls_made).lower()}</td></tr></table></div>
<div class="card s6"><h2>Interpretation boundary</h2><ul>{warnings}</ul><div class="subtle">Research state: {escape(report.research_state)}. Flexible strategy design does not turn exploratory output into validated edge.</div></div>
</div>"""


def _entry_detail(report: StrategyBuilderReport) -> str:
    if report.feature_strategy_report is not None:
        strategy = report.feature_strategy_report.strategy
        return f"""<table><tr><th>Compiled expression</th><td><code>{escape(strategy.expression)}</code></td></tr><tr><th>Ranking metric</th><td>{escape(_rank_label(strategy.rank_feature))}</td></tr><tr><th>Direction</th><td>{'highest first' if strategy.descending else 'lowest first'}</td></tr><tr><th>Per-day signal cap</th><td>{strategy.per_session_limit}</td></tr><tr><th>Feature set</th><td><code>{escape(report.feature_strategy_report.feature_set_version)}</code></td></tr></table>"""
    config = report.consolidation_config
    if config is None:
        return "<div class='subtle'>Entry definition unavailable.</div>"
    volume = "none" if config.min_breakout_volume_ratio is None else f"{config.min_breakout_volume_ratio:g}x"
    return f"""<table><tr><th>Duration</th><td>{config.duration} trading days</td></tr><tr><th>Max range</th><td>{config.max_range_pct * 100:.1f}%</td></tr><tr><th>Trend</th><td>{escape(config.trend_filter.value)}</td></tr><tr><th>Volume gate</th><td>{escape(volume)}</td></tr></table>"""


def _row(item: ExitPolicySummary) -> str:
    return "<tr>" + f"<td><strong>{escape(_label(item))}</strong><br><span class='blue'>{escape(item.family.value)}</span></td>" + f"<td>{item.sample_size}</td><td>{_prob(item.stop_out_rate)}</td>" + f"<td class='{_value_class(item.expectancy)}'>{_pct(item.expectancy)}</td>" + f"<td class='{_value_class(item.expectancy_delta_vs_hold)}'>{_pct(item.expectancy_delta_vs_hold)}</td>" + f"<td>{_prob(item.win_probability)}</td><td>{_num(item.profit_factor)}</td>" + f"<td>{_num(item.payoff_ratio)}</td><td>{_pct(item.tail_loss_p05)}</td>" + f"<td>{_num(item.average_holding_period_sessions)}</td><td>{_num(item.median_holding_period_sessions)}</td>" + f"<td>{_pct(item.median_mae_before_exit)}</td><td>{_pct(item.median_mfe_full_horizon)}</td>" + f"<td>{_pct(item.median_max_drawdown_before_exit)}</td><td>{_prob(item.gap_through_frequency)}</td></tr>"


def _label(item: ExitPolicySummary) -> str:
    if item.family is ExitFamily.HOLD_TO_HORIZON:
        return "Hold to outcome horizon"
    if item.family is ExitFamily.FIXED_PERCENT_STOP:
        return f"Fixed {item.resolved_parameters['distance_pct'] * 100:g}% stop"
    if item.family is ExitFamily.TRAILING_PERCENT_STOP:
        return f"Trailing {item.resolved_parameters['distance_pct'] * 100:g}% stop"
    if item.family is ExitFamily.ATR_STOP:
        return f"ATR {item.resolved_parameters['atr_multiple']:g}x stop"
    return f"Trailing ATR {item.resolved_parameters['atr_multiple']:g}x stop"


def _rank_label(value: str) -> str:
    labels = {
        "return_5": "5-day Price ROC",
        "return_20": "20-day Price ROC",
        "return_252": "252-day Price ROC",
        "relative_volume_20": "20-day Relative Volume (RVOL)",
        "average_dollar_volume_20": "20-day Average Dollar Volume",
        "atr_pct_14": "ATR(14) % of Price",
        "realized_volatility_20": "20-day Historical Volatility",
        "distance_sma_20_pct": "Price vs SMA(20)",
        "distance_sma_50_pct": "Price vs SMA(50)",
        "distance_sma_200_pct": "Price vs SMA(200)",
        "rsi_wilder_14": "RSI(14)",
        "macd_histogram_pct": "MACD Histogram (12,26,9)",
        "distance_prior_high_20_pct": "Price vs Prior 20-day High",
        "distance_prior_high_55_pct": "Price vs Prior 55-day High",
    }
    return labels.get(value, value.replace("_", " "))


def _integer_options(values: tuple[int, ...], selected: int, suffix: str) -> str:
    return "".join(f'<option value="{value}"' + (" selected" if value == selected else "") + f">{value}{suffix}</option>" for value in values)


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
