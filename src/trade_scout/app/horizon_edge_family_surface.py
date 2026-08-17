# ruff: noqa: E501
"""Presentation-only HTML for the controlled holding-horizon edge family."""

from __future__ import annotations

from html import escape

from trade_scout.statistics.horizon_edge_family import HorizonEdgeFamilyReport
from trade_scout.statistics.readable_edge import ConfidenceInterval


def render_horizon_edge_family_html(
    report: HorizonEdgeFamilyReport,
    *,
    report_checksum: str | None = None,
) -> str:
    rows = "".join(_row(item) for item in report.horizon_results)
    candidate_text = (
        ", ".join(f"{value} sessions" for value in report.candidate_horizons)
        if report.candidate_horizons
        else "None"
    )
    checksum_row = (
        f"<tr><th>Report checksum</th><td><code>{escape(report_checksum)}</code></td></tr>"
        if report_checksum
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Holding Horizon Edge Family</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.48 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
.wrap {{ width:min(1650px,96vw); margin:auto; padding:28px 0 70px; }} header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }} h1 {{ margin:0; font-size:31px; }} h2 {{ margin:0 0 9px; font-size:18px; }}
.subtle {{ color:var(--muted); }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:6px 10px; font-size:11px; font-weight:800; }}
.card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} .verdict {{ border-color:#68551f; background:#1d190c; padding:20px; }} .verdict-code {{ color:var(--accent); font-size:12px; font-weight:850; letter-spacing:.08em; }} .verdict h2 {{ font-size:24px; margin:5px 0 7px; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; vertical-align:top; white-space:nowrap; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} th:first-child,td:first-child {{ text-align:left; }} tr:last-child td {{ border-bottom:0; }} .scroll {{ overflow:auto; }}
.good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .warn {{ color:var(--warn); }} .blue {{ color:var(--blue); }} .pass {{ background:rgba(99,211,154,.08); }} .fail {{ background:rgba(239,123,123,.05); }} code {{ color:#d9e3ef; overflow-wrap:anywhere; white-space:normal; }} ul {{ margin-bottom:0; }}
@media(max-width:900px) {{ header {{ display:block; }} .pill {{ margin-top:10px; }} }}
@media print {{ :root {{ color-scheme:light; }} body {{ background:white; color:#111; }} .card {{ break-inside:avoid; background:white; border-color:#aaa; }} .subtle,th {{ color:#555; }} }}
</style>
</head>
<body><div class="wrap">
<header><div><h1>Holding Horizon Edge Family</h1><div class="subtle">One fixed consolidation-breakout definition, seven predeclared holding horizons, explicit control comparisons and within-family multiplicity correction.</div></div><span class="pill">{escape(report.research_state)} · {escape(report.report_definition_version)}</span></header>
<div class="card verdict"><div class="verdict-code">{escape(report.verdict.code)}</div><h2>{escape(report.verdict.headline)}</h2><div>{escape(report.verdict.explanation)}</div></div>
<div class="card"><h2>Family verdict at a glance</h2><table>
<tr><th>Horizon family</th><td>{escape(', '.join(str(value) for value in report.horizon_family))} daily sessions</td></tr>
<tr><th>Multiplicity method</th><td>{escape(report.multiplicity_method.value)} across {len(report.horizon_family)} horizon hypotheses</td></tr>
<tr><th>Alpha</th><td>{report.alpha:.3f}</td></tr>
<tr><th>Preliminary candidate horizons</th><td>{escape(candidate_text)}</td></tr>
<tr><th>Lowest BH-adjusted p-value horizon</th><td>{report.lowest_adjusted_p_horizon} sessions</td></tr>
<tr><th>Best observed random-timing excess horizon</th><td>{report.best_observed_random_excess_horizon} sessions</td></tr>
<tr><th>Broader strategy-family correction</th><td>{escape(report.broader_research_family_correction_status)}</td></tr>
<tr><th>Out of sample</th><td>{escape(report.out_of_sample_status)}</td></tr>
</table></div>
<div class="card"><h2>Edge by holding horizon</h2><div class="subtle">A horizon passes this preliminary family gate only if it has positive excess versus the current trend-context control, positive excess versus randomized eligible timing, a BH-adjusted random-timing p-value below alpha, and a month-clustered raw-mean interval fully above zero.</div><div class="scroll"><table><thead><tr><th>Horizon</th><th>N</th><th>Raw mean</th><th>Raw 95% CI</th><th>Win rate</th><th>Expectancy</th><th>PF</th><th>Baseline mean</th><th>Excess vs baseline</th><th>Baseline excess 95% CI</th><th>Random null</th><th>Random excess</th><th>Raw p</th><th>BH p</th><th>Gate</th></tr></thead><tbody>{rows}</tbody></table></div></div>
<div class="card"><h2>Interpretation boundary</h2><ul><li>This corrects only the seven predeclared holding-horizon tests shown here.</li><li>It does not correct for prior or future searches over trend definitions, pattern timeframe, duration, tightness, volume confirmation, stop rules, instruments, sectors or regimes.</li><li>A passing horizon remains EXPLORATORY until the broader research family is accounted for and the frozen candidate survives genuine out-of-sample validation.</li></ul></div>
<div class="card"><h2>Run provenance</h2><table>
<tr><th>Universe</th><td>{escape(report.universe_label)}</td></tr><tr><th>Universe ID</th><td><code>{escape(report.universe_id)}</code></td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Analysis window</th><td>{report.analysis_start.isoformat()} → {report.analysis_end.isoformat()}</td></tr><tr><th>Pattern timeframe</th><td>{escape(report.pattern_timeframe.value)}</td></tr><tr><th>Base duration</th><td>{report.selected_config.duration} pattern bars</td></tr><tr><th>Max base range</th><td>{report.selected_config.max_range_pct * 100:.1f}%</td></tr><tr><th>Trend filter</th><td>{escape(report.selected_config.trend_filter.value)}</td></tr><tr><th>Bootstrap resamples</th><td>{report.bootstrap_resamples}</td></tr><tr><th>Random iterations</th><td>{report.random_iterations}</td></tr><tr><th>Root seed</th><td>{report.random_seed}</td></tr>{checksum_row}</table></div>
</div></body></html>"""


def _row(item) -> str:
    performance = item.performance
    baseline = item.simple_baseline
    randomized = item.randomized_timing
    css = "pass" if item.preliminary_gate_passed else "fail"
    gate = "PASS" if item.preliminary_gate_passed else "; ".join(item.gate_failures)
    return (
        f'<tr class="{css}"><td><strong>{item.horizon}</strong></td>'
        f"<td>{performance.sample_size}</td>"
        f"<td class='{_value_class(performance.mean_return)}'>{_pct(performance.mean_return)}</td>"
        f"<td>{_interval(performance.mean_interval)}</td>"
        f"<td>{_prob(performance.win_rate)}</td>"
        f"<td>{_pct(performance.expectancy)}</td>"
        f"<td>{_num(performance.profit_factor)}</td>"
        f"<td>{_pct(baseline.mean_return)}</td>"
        f"<td class='{_value_class(baseline.excess_mean_return)}'>{_pct(baseline.excess_mean_return)}</td>"
        f"<td>{_interval(baseline.excess_interval)}</td>"
        f"<td>{_pct(randomized.null_mean_return)}</td>"
        f"<td class='{_value_class(randomized.excess_vs_null_mean)}'>{_pct(randomized.excess_vs_null_mean)}</td>"
        f"<td>{randomized.one_sided_p_value:.4f}</td>"
        f"<td>{item.adjusted_random_timing_p_value:.4f}</td>"
        f"<td>{escape(gate)}</td></tr>"
    )


def _interval(interval: ConfidenceInterval | None) -> str:
    if interval is None:
        return "—"
    return f"{_pct(interval.lower)} to {_pct(interval.upper)}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _prob(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _value_class(value: float | None) -> str:
    if value is None:
        return "warn"
    return "good" if value > 0 else "bad" if value < 0 else ""


__all__ = ["render_horizon_edge_family_html"]
