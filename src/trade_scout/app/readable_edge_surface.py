# ruff: noqa: E501
"""Presentation-only HTML for the readable market-wide edge audit."""

from __future__ import annotations

from html import escape

from trade_scout.statistics.readable_edge import ConfidenceInterval, ReadableEdgeReport


def render_readable_edge_html(
    report: ReadableEdgeReport,
    *,
    report_checksum: str | None = None,
) -> str:
    source = report.source_report
    performance = report.performance
    baseline = report.simple_baseline
    randomized = report.randomized_timing
    parameters = report.parameter_robustness

    mean_ci = _interval(performance.mean_interval, percent=True)
    win_ci = _interval(performance.win_rate_interval, percent=True, probability=True)
    excess_ci = _interval(baseline.excess_interval, percent=True)
    cost_rows = "".join(
        "<tr>"
        f"<td>{item.round_trip_bps} bps</td>"
        f"<td class='{_value_class(item.net_mean_return)}'>{_pct(item.net_mean_return)}</td>"
        "</tr>"
        for item in report.cost_sensitivity
    )
    horizon_rows = "".join(
        "<tr>"
        f"<td>{item.horizon}</td><td>{item.sample_size}</td>"
        f"<td>{_pct(item.mean_return)}</td><td>{_pct(item.median_return)}</td>"
        f"<td>{_prob(item.positive_fraction)}</td>"
        f"<td>{_pct(item.median_mfe)}</td><td>{_pct(item.median_mae)}</td>"
        "</tr>"
        for item in source.horizon_summaries
    )
    checksum_row = (
        f"<tr><th>Report checksum</th><td><code>{escape(report_checksum)}</code></td></tr>"
        if report_checksum
        else ""
    )
    best_parameter = (
        "—"
        if parameters.best_cell_duration is None
        else (
            f"{parameters.best_cell_duration} bars / "
            f"{parameters.best_cell_max_range_pct * 100:.0f}% range / "
            f"{_pct(parameters.best_cell_excess)} excess"
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Readable Edge Audit</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; --warn:#f2bd60; --blue:#7fc8ff; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; font:14px/1.48 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }}
.wrap {{ width:min(1500px,96vw); margin:auto; padding:28px 0 70px; }}
header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }}
h1 {{ margin:0; font-size:31px; }} h2 {{ margin:0 0 9px; font-size:18px; }}
.subtle {{ color:var(--muted); }} .pill {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:6px 10px; font-size:11px; font-weight:800; }}
.card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; min-width:0; }}
.grid {{ display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:14px; margin-top:14px; }}
.s3 {{ grid-column:span 3; }} .s4 {{ grid-column:span 4; }} .s6 {{ grid-column:span 6; }} .s8 {{ grid-column:span 8; }} .s12 {{ grid-column:1/-1; }}
.verdict {{ border-color:#68551f; background:#1d190c; padding:20px; margin-top:16px; }}
.verdict-code {{ color:var(--accent); font-size:12px; font-weight:850; letter-spacing:.08em; }}
.verdict h2 {{ font-size:24px; margin:5px 0 7px; }}
.metric-label {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.06em; }} .metric {{ font-size:23px; font-weight:780; margin-top:4px; }}
.good {{ color:var(--good); }} .bad {{ color:var(--bad); }} .warn {{ color:var(--warn); }} .blue {{ color:var(--blue); }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:left; vertical-align:top; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} tr:last-child td,tr:last-child th {{ border-bottom:0; }}
code {{ color:#d9e3ef; overflow-wrap:anywhere; }} .status {{ display:grid; gap:7px; }} .status-row {{ display:flex; justify-content:space-between; gap:12px; border-bottom:1px solid var(--border); padding-bottom:7px; }} .status-row:last-child {{ border:0; padding-bottom:0; }}
ul {{ padding-left:20px; margin-bottom:0; }} .scroll {{ overflow:auto; }}
@media(max-width:1100px) {{ .s3,.s4,.s6,.s8 {{ grid-column:1/-1; }} header {{ display:block; }} .pill {{ margin-top:10px; }} }}
@media print {{ :root {{ color-scheme:light; }} body {{ background:white; color:#111; }} .card {{ break-inside:avoid; background:white; border-color:#aaa; }} .subtle,th {{ color:#555; }} }}
</style>
</head>
<body><div class="wrap">
<header>
  <div><h1>Readable Edge Audit</h1><div class="subtle">Market-wide economic edge, uncertainty, controls, cost sensitivity and parameter stability — without upgrading the formal research state.</div></div>
  <span class="pill">{escape(report.research_state)} · {escape(report.report_definition_version)}</span>
</header>

<div class="card verdict">
  <div class="verdict-code">{escape(report.verdict.code)}</div>
  <h2>{escape(report.verdict.headline)}</h2>
  <div>{escape(report.verdict.explanation)}</div>
</div>

<div class="grid">
  <div class="card s3"><div class="metric-label">Raw {source.selected_horizon}-day mean</div><div class="metric {_value_class(performance.mean_return)}">{_pct(performance.mean_return)}</div><div class="subtle">95% month-cluster CI {mean_ci} · n={performance.sample_size}</div></div>
  <div class="card s3"><div class="metric-label">Excess vs simple baseline</div><div class="metric {_value_class(baseline.excess_mean_return)}">{_pct(baseline.excess_mean_return)}</div><div class="subtle">95% paired-month CI {excess_ci}</div></div>
  <div class="card s3"><div class="metric-label">Random timing excess</div><div class="metric {_value_class(randomized.excess_vs_null_mean)}">{_pct(randomized.excess_vs_null_mean)}</div><div class="subtle">one-sided p={randomized.one_sided_p_value:.4f} · {randomized.iterations} iterations</div></div>
  <div class="card s3"><div class="metric-label">Expectancy</div><div class="metric {_value_class(performance.expectancy)}">{_pct(performance.expectancy)}</div><div class="subtle">PF {_num(performance.profit_factor)} · payoff {_num(performance.payoff_ratio)}</div></div>

  <div class="card s3"><div class="metric-label">Win rate</div><div class="metric">{_prob(performance.win_rate)}</div><div class="subtle">95% Wilson CI {win_ci}</div></div>
  <div class="card s3"><div class="metric-label">Parameter cells above baseline</div><div class="metric">{parameters.positive_excess_cell_count}/{parameters.searched_cell_count}</div><div class="subtle">{_prob(parameters.positive_excess_cell_fraction)} of searched duration/range cells</div></div>
  <div class="card s3"><div class="metric-label">Break-even friction</div><div class="metric">{_bps(report.break_even_round_trip_bps)}</div><div class="subtle">mechanical round-trip friction that reduces raw mean to zero</div></div>
  <div class="card s3"><div class="metric-label">Cross-stock breadth</div><div class="metric">{_prob(source.instrument_breadth_fraction)}</div><div class="subtle">{source.instruments_with_events}/{source.universe_instrument_count} instruments with events</div></div>

  <div class="card s8">
    <h2>Economic performance</h2>
    <table>
      <tr><th>Complete outcomes</th><td>{performance.sample_size}</td><th>Mean</th><td>{_pct(performance.mean_return)}</td></tr>
      <tr><th>Median</th><td>{_pct(performance.median_return)}</td><th>Std dev</th><td>{_pct(performance.standard_deviation)}</td></tr>
      <tr><th>Average win</th><td>{_pct(performance.average_win)}</td><th>Average loss</th><td>{_pct_negative(performance.average_loss)}</td></tr>
      <tr><th>Payoff ratio</th><td>{_num(performance.payoff_ratio)}</td><th>Profit factor</th><td>{_num(performance.profit_factor)}</td></tr>
      <tr><th>P05 / P95</th><td>{_pct(performance.p05_return)} / {_pct(performance.p95_return)}</td><th>P25 / P75</th><td>{_pct(performance.p25_return)} / {_pct(performance.p75_return)}</td></tr>
      <tr><th>Worst / best</th><td>{_pct(performance.minimum_return)} / {_pct(performance.maximum_return)}</td><th>Top-five winner share</th><td>{_prob(performance.top_five_profit_share)}</td></tr>
      <tr><th>Skewness</th><td>{_num(performance.skewness)}</td><th>Excess kurtosis</th><td>{_num(performance.excess_kurtosis)}</td></tr>
    </table>
  </div>
  <div class="card s4">
    <h2>Validation gates</h2>
    <div class="status">
      <div class="status-row"><span>Research state</span><strong>{escape(report.research_state)}</strong></div>
      <div class="status-row"><span>Out of sample</span><strong>{escape(report.out_of_sample_status)}</strong></div>
      <div class="status-row"><span>Multiple testing</span><strong>{escape(report.multiple_testing_status)}</strong></div>
      <div class="status-row"><span>Portfolio simulation</span><strong>{escape(report.portfolio_status)}</strong></div>
    </div>
    <div class="subtle" style="margin-top:10px">A favorable preliminary readout cannot override an incomplete critical gate.</div>
  </div>

  <div class="card s6">
    <h2>Control 1 — current trend-context baseline</h2>
    <table>
      <tr><th>Control mean</th><td>{_pct(baseline.mean_return)}</td></tr>
      <tr><th>Control n</th><td>{baseline.sample_size}</td></tr>
      <tr><th>Strategy excess</th><td class="{_value_class(baseline.excess_mean_return)}">{_pct(baseline.excess_mean_return)}</td></tr>
      <tr><th>95% excess CI</th><td>{excess_ci}</td></tr>
      <tr><th>Definition</th><td>{escape(baseline.comparator_description)}</td></tr>
    </table>
    <div class="subtle" style="margin-top:9px">This retains the existing baseline for continuity. It is still descriptive rather than a fully matched independent benchmark.</div>
  </div>
  <div class="card s6">
    <h2>Control 2 — randomized eligible timing</h2>
    <table>
      <tr><th>Null mean</th><td>{_pct(randomized.null_mean_return)}</td></tr>
      <tr><th>Null 95% range</th><td>{_pct(randomized.null_p025)} → {_pct(randomized.null_p975)}</td></tr>
      <tr><th>Strategy excess</th><td class="{_value_class(randomized.excess_vs_null_mean)}">{_pct(randomized.excess_vs_null_mean)}</td></tr>
      <tr><th>One-sided p-value</th><td>{randomized.one_sided_p_value:.4f}</td></tr>
      <tr><th>Matched events / candidates</th><td>{randomized.matched_event_count} / {randomized.eligible_candidate_count}</td></tr>
      <tr><th>Seed</th><td><code>{randomized.random_seed}</code></td></tr>
    </table>
    <div class="subtle" style="margin-top:9px">{escape(randomized.comparator_description)}</div>
  </div>

  <div class="card s6">
    <h2>Parameter robustness — first readable pass</h2>
    <table>
      <tr><th>Alternatives searched</th><td>{parameters.searched_cell_count}</td></tr>
      <tr><th>Cells above baseline</th><td>{parameters.positive_excess_cell_count} ({_prob(parameters.positive_excess_cell_fraction)})</td></tr>
      <tr><th>Selected cell excess</th><td>{_pct(parameters.selected_cell_excess)}</td></tr>
      <tr><th>Positive adjacent cells</th><td>{_prob(parameters.selected_positive_neighbor_fraction)} across {parameters.selected_neighbor_count} neighbours</td></tr>
      <tr><th>Best observed cell</th><td>{escape(best_parameter)}</td></tr>
    </table>
    <div class="subtle" style="margin-top:9px">This is a neighbourhood diagnostic, not a multiple-testing correction. The search count is shown explicitly so the best-looking cell cannot be read as independent evidence.</div>
  </div>
  <div class="card s6">
    <h2>Mechanical cost sensitivity</h2>
    <table><thead><tr><th>Round-trip friction</th><th>Mean after friction</th></tr></thead><tbody>{cost_rows}</tbody></table>
    <div class="subtle" style="margin-top:9px">This only subtracts round-trip bps from event returns. It is not the later spread/slippage/liquidity/portfolio execution engine.</div>
  </div>

  <div class="card s12">
    <h2>Forward horizon context</h2>
    <div class="subtle">The verdict above concerns the selected {source.selected_horizon}-session horizon. Other horizons remain descriptive context.</div>
    <div class="scroll"><table><thead><tr><th>Daily horizon</th><th>n</th><th>Mean</th><th>Median</th><th>P(return&gt;0)</th><th>Median MFE</th><th>Median MAE</th></tr></thead><tbody>{horizon_rows}</tbody></table></div>
  </div>

  <div class="card s6">
    <h2>Run definition</h2>
    <table>
      <tr><th>Universe</th><td>{escape(source.universe_label)}</td></tr>
      <tr><th>Dataset</th><td><code>{escape(source.dataset_version)}</code></td></tr>
      <tr><th>Analysis window</th><td>{source.analysis_start.isoformat()} → {source.analysis_end.isoformat()}</td></tr>
      <tr><th>Base duration</th><td>{source.selected_config.duration} pattern bars</td></tr>
      <tr><th>Max base range</th><td>{source.selected_config.max_range_pct * 100:.1f}%</td></tr>
      <tr><th>Trend filter</th><td><code>{escape(source.selected_config.trend_filter.value)}</code></td></tr>
      <tr><th>Selected horizon</th><td>{source.selected_horizon} daily sessions</td></tr>
      <tr><th>Strategy version</th><td><code>{escape(source.strategy_version)}</code></td></tr>
      {checksum_row}
    </table>
  </div>
  <div class="card s6">
    <h2>What is still missing before “real edge” becomes validated edge?</h2>
    <ul>
      <li>Matched market/sector benchmarks and factor attribution.</li>
      <li>Stop/target selection validated on untouched data.</li>
      <li>Formal multiple-testing/data-snooping correction for the parameter and strategy family.</li>
      <li>Walk-forward / genuine out-of-sample retention.</li>
      <li>Point-in-time sector/regime conditioning and evidence-ranked instruments.</li>
      <li>Portfolio overlap, sizing, slippage, liquidity, concentration and capital constraints.</li>
    </ul>
  </div>

  <div class="card s12">
    <h2>Audit note</h2>
    <div>The readable layer first reconstructs the selected strategy and current simple baseline and fails if their sample counts or means do not reproduce the existing market-wide report. Statistical additions therefore sit on top of the current report instead of silently changing its event population.</div>
  </div>
</div>
</div></body></html>"""


def _interval(
    interval: ConfidenceInterval | None,
    *,
    percent: bool,
    probability: bool = False,
) -> str:
    if interval is None:
        return "—"
    formatter = _prob if probability else _pct if percent else _num
    return f"{formatter(interval.lower)} to {formatter(interval.upper)}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _pct_negative(value: float | None) -> str:
    return "—" if value is None else f"-{value * 100:.2f}%"


def _prob(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def _bps(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} bps"


def _value_class(value: float | None) -> str:
    if value is None:
        return "warn"
    return "good" if value > 0 else "bad" if value < 0 else ""


__all__ = ["render_readable_edge_html"]
