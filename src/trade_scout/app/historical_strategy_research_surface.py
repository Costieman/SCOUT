# ruff: noqa: E501
"""Presentation-only HTML for historical strategy research."""

from __future__ import annotations

from html import escape

from trade_scout.app.historical_strategy_research_service import HistoricalStrategyResearchReport
from trade_scout.app.strategy_definition import STRATEGY_LIBRARY, StrategyDefinition


def render_historical_strategy_research_html(
    *,
    selected_strategy_id: str | None = None,
    report: HistoricalStrategyResearchReport | None = None,
    error: str | None = None,
) -> str:
    selected = selected_strategy_id or STRATEGY_LIBRARY[0].strategy_id
    strategy = _strategy_by_id(selected)
    warning = (
        f'<div class="error"><strong>Cannot run strategy research:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    body = _render_report(report) if report is not None else _empty_state()
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Strategy Research</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1450px,96vw); margin:auto; padding:28px 0 70px; }} h1 {{ margin:0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} form {{ display:flex; gap:10px; align-items:end; flex-wrap:wrap; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; min-width:300px; }} select,button {{ border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} code {{ display:block; margin-top:8px; padding:10px; border-radius:8px; background:var(--panel2); overflow:auto; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; }} th:first-child,td:first-child {{ text-align:left; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} .metrics {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }} .metric {{ font-size:24px; font-weight:760; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }} @media(max-width:850px) {{ .metrics {{ grid-template-columns:1fr; }} }}
</style></head><body><div class="wrap">
<a href="/">← Research console</a><h1>Historical Strategy Research</h1>
<div class="subtle">Point-in-time cross-sectional signals with next-session split-adjusted-open forward outcomes. This is descriptive research, not a portfolio backtest: position sizing, overlap rules, transaction costs, taxes and capital constraints are not modeled.</div>
<div class="card"><form action="/research/strategies" method="get"><label>Named strategy<select name="strategy">{_strategy_options(selected)}</select></label><button type="submit">Run historical research</button></form></div>
<div class="card"><h2>{escape(strategy.name)}</h2><div>{escape(strategy.description)}</div><div class="subtle">Rank: {escape(strategy.sort_by)} · {"descending" if strategy.descending else "ascending"} · maximum {strategy.limit} symbols/session</div><code>{escape(strategy.expression)}</code></div>
{warning}{body}
</div></body></html>"""


def _empty_state() -> str:
    return '<div class="card"><h2>Ready</h2><div class="subtle">Choose a named immutable strategy and run point-in-time historical signal/outcome research over the reviewed canonical universe.</div></div>'


def _render_report(report: HistoricalStrategyResearchReport) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{item.horizon} sessions</td>"
        f"<td>{item.sample_size}</td>"
        f"<td>{_percent(item.mean_return)}</td>"
        f"<td>{_percent(item.median_return)}</td>"
        f"<td>{_fraction(item.positive_fraction)}</td>"
        f"<td>{_percent(item.median_mfe)}</td>"
        f"<td>{_percent(item.median_mae)}</td>"
        f"<td>{_percent(item.median_max_drawdown)}</td>"
        "</tr>"
        for item in report.summaries
    )
    return f"""<div class="metrics card"><div><div class="subtle">Reviewed instruments</div><div class="metric">{report.instrument_count}</div></div><div><div class="subtle">Selected signal rows</div><div class="metric">{report.signal_count}</div></div><div><div class="subtle">Measured signal/horizon outcomes</div><div class="metric">{len(report.outcomes)}</div></div></div>
<div class="card" style="overflow:auto"><h2>Forward outcome distributions</h2><table><thead><tr><th>Horizon</th><th>N</th><th>Mean return</th><th>Median return</th><th>Positive</th><th>Median MFE</th><th>Median MAE</th><th>Median max drawdown</th></tr></thead><tbody>{rows}</tbody></table></div>"""


def _strategy_options(selected: str) -> str:
    return "".join(
        f'<option value="{escape(item.strategy_id)}"'
        + (" selected" if item.strategy_id == selected else "")
        + f">{escape(item.name)}</option>"
        for item in STRATEGY_LIBRARY
    )


def _strategy_by_id(strategy_id: str) -> StrategyDefinition:
    for item in STRATEGY_LIBRARY:
        if item.strategy_id == strategy_id:
            return item
    return STRATEGY_LIBRARY[0]


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _fraction(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


__all__ = ["render_historical_strategy_research_html"]
