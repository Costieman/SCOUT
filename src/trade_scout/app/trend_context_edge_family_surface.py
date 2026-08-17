# ruff: noqa: E501
"""Presentation-only HTML for the canonical-only T0-T5 trend-context family."""

from __future__ import annotations

from html import escape

from trade_scout.validation.trend_context_edge_family import (
    Interval,
    TrendContextEdgeFamilyReport,
)


def render_trend_context_edge_family_html(
    report: TrendContextEdgeFamilyReport, *, report_checksum: str | None = None
) -> str:
    rows = "".join(_row(item) for item in report.context_results)
    candidates = ", ".join(item.value for item in report.candidate_contexts) or "None"
    checksum = escape(report_checksum) if report_checksum else "—"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Trend Context Edge Family</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.48 system-ui,-apple-system,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
.wrap {{ width:min(1650px,96vw); margin:auto; padding:28px 0 70px; }} h1 {{ margin:0; font-size:31px; }} h2 {{ margin:0 0 9px; font-size:18px; }}
.subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} .verdict {{ border-color:#68551f; background:#1d190c; padding:20px; }} .verdict-code {{ color:var(--accent); font-size:12px; font-weight:850; letter-spacing:.08em; }} .verdict h2 {{ font-size:24px; margin:5px 0 7px; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; vertical-align:top; white-space:nowrap; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} th:first-child,td:first-child {{ text-align:left; }} .scroll {{ overflow:auto; }} .good {{ color:var(--good); }} .bad {{ color:var(--bad); }} code {{ color:#d9e3ef; }}
@media print {{ :root {{ color-scheme:light; }} body {{ background:white; color:#111; }} .card {{ background:white; border-color:#aaa; break-inside:avoid; }} .subtle,th {{ color:#555; }} }}
</style></head><body><div class="wrap">
<h1>Trend Context Edge Family</h1><div class="subtle">Canonical-only T0–T5 decomposition. Each child rule is compared with its predeclared parent rule while the horizon, entry convention, stride and numerical lookbacks stay fixed.</div>
<div class="card verdict"><div class="verdict-code">{escape(report.verdict.code)}</div><h2>{escape(report.verdict.headline)}</h2><div>{escape(report.verdict.explanation)}</div></div>
<div class="card"><h2>Family verdict</h2><table><tr><th>Preliminary candidate contexts</th><td>{escape(candidates)}</td></tr><tr><th>Multiplicity</th><td>{escape(report.multiplicity_method.value)} across T1–T5 parent-increment hypotheses</td></tr><tr><th>Selected horizon</th><td>{report.horizon} sessions</td></tr><tr><th>T6 market-relative strength</th><td>{escape(report.t6_market_benchmark_status)}</td></tr><tr><th>Out of sample</th><td>{escape(report.out_of_sample_status)}</td></tr></table></div>
<div class="card"><h2>Trend decomposition</h2><div class="subtle">Parent map: T1→T0, T2→T1, T3→T1, T4→T3, T5→T2. Parent increment is the average of paired calendar-month child-minus-parent means. T0 is the unconditional reference and is not itself a tested increment.</div><div class="scroll"><table><thead><tr><th>Context</th><th>Parent</th><th>N</th><th>Mean</th><th>Raw 95% CI</th><th>Median</th><th>Win rate</th><th>PF</th><th>Median MFE</th><th>Median MAE</th><th>Parent mean</th><th>Paired-month increment</th><th>Increment 95% CI</th><th>Raw p</th><th>BH p</th><th>Gate</th></tr></thead><tbody>{rows}</tbody></table></div></div>
<div class="card"><h2>Trend definitions</h2><ul><li>T0: no trend filter.</li><li>T1: close above 200-session SMA.</li><li>T2: T1 plus rising 200-session SMA over {report.trend_config.sma_slope_lookback} sessions.</li><li>T3: close above both 50- and 200-session SMAs.</li><li>T4: T3 plus 50-session SMA above 200-session SMA.</li><li>T5: T2 plus positive trailing {report.trend_config.trailing_return_intervals}-session return.</li><li>T6 is deliberately omitted because the explicit market benchmark is not present in the selected canonical dataset.</li></ul></div>
<div class="card"><h2>Run provenance</h2><table><tr><th>Universe</th><td>{escape(report.universe_label)}</td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Window</th><td>{report.analysis_start.isoformat()} → {report.analysis_end.isoformat()}</td></tr><tr><th>Stride</th><td>{report.sampling_stride} sessions</td></tr><tr><th>Bootstrap resamples</th><td>{report.bootstrap_resamples}</td></tr><tr><th>Randomization iterations</th><td>{report.randomization_iterations}</td></tr><tr><th>Root seed</th><td>{report.random_seed}</td></tr><tr><th>Checksum</th><td><code>{checksum}</code></td></tr></table></div>
<div class="card"><h2>Interpretation boundary</h2><div>This is exploratory fixed-cohort evidence. It does not claim historical S&amp;P 500 membership, survivorship-bias-free validation, market-relative T6 evidence, full strategy-family multiplicity correction or out-of-sample confirmation.</div></div>
</div></body></html>"""


def _row(item) -> str:
    parent = item.parent_context.value if item.parent_context is not None else "—"
    raw_p = _num(item.raw_parent_randomization_p_value, 4)
    adj_p = _num(item.adjusted_parent_randomization_p_value, 4)
    gate = (
        "REFERENCE"
        if item.parent_context is None
        else ("PASS" if item.preliminary_gate_passed else "; ".join(item.gate_failures))
    )
    return (
        f"<tr><td><strong>{escape(item.context.value)}</strong></td><td>{escape(parent)}</td>"
        f"<td>{item.sample_size}</td><td class='{_value_class(item.mean_return)}'>{_pct(item.mean_return)}</td>"
        f"<td>{_interval(item.mean_interval)}</td><td>{_pct(item.median_return)}</td><td>{item.win_rate * 100:.1f}%</td>"
        f"<td>{_num(item.profit_factor, 3)}</td><td>{_pct(item.median_mfe)}</td><td>{_pct(item.median_mae)}</td>"
        f"<td>{_pct(item.parent_mean_return)}</td><td class='{_value_class(item.paired_month_excess)}'>{_pct(item.paired_month_excess)}</td>"
        f"<td>{_interval(item.paired_month_excess_interval)}</td><td>{raw_p}</td><td>{adj_p}</td><td>{escape(gate)}</td></tr>"
    )


def _interval(value: Interval | None) -> str:
    return "—" if value is None else f"{_pct(value.lower)} to {_pct(value.upper)}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _num(value: float | None, digits: int) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _value_class(value: float | None) -> str:
    if value is None:
        return ""
    return "good" if value > 0 else "bad" if value < 0 else ""


__all__ = ["render_trend_context_edge_family_html"]
