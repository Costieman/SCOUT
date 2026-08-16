# ruff: noqa: E501
"""Presentation-only HTML for the canonical-data strategy research workbench."""

from __future__ import annotations

from html import escape

from trade_scout.app.strategy_research_service import StrategyResearchRequest
from trade_scout.statistics.strategy_research import StrategyResearchReport

_DEFAULT_EXPRESSION = (
    "return_20 >= 0.05 and relative_volume_20 >= 1.5 and distance_sma_200_pct > 0"
)


def render_strategy_research_html(
    *,
    symbols: tuple[str, ...],
    features: tuple[str, ...],
    request: StrategyResearchRequest | None = None,
    report: StrategyResearchReport | None = None,
    error: str | None = None,
) -> str:
    """Render a read-only form and descriptive results without analytical logic."""

    expression = request.expression if request is not None else _DEFAULT_EXPRESSION
    rank_feature = request.rank_feature if request is not None else "return_20"
    lookback_years = request.lookback_years if request is not None else 5
    limit = request.per_session_limit if request is not None else 25
    horizons = request.horizons if request is not None else (5, 20, 60)
    selected_symbols = request.symbols if request is not None else ()
    descending = request.descending if request is not None else True
    warning = (
        f'<div class="error"><strong>Cannot run strategy research:</strong> {escape(error)}</div>'
        if error
        else ""
    )
    results = _render_report(report) if report is not None else _empty_state()
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Scout — Strategy Lab</title>
<style>
:root {{ color-scheme:dark; --bg:#0b0e13; --panel:#121720; --panel2:#171d27; --border:#293241; --text:#edf1f7; --muted:#98a6b8; --accent:#f1c84b; --good:#63d39a; --bad:#ef7b7b; }}
* {{ box-sizing:border-box; }} body {{ margin:0; font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--text); }} a {{ color:var(--accent); text-decoration:none; }} .wrap {{ width:min(1500px,96vw); margin:auto; padding:28px 0 70px; }} h1 {{ margin:5px 0 0; font-size:30px; }} h2 {{ margin:0 0 10px; font-size:18px; }} .subtle {{ color:var(--muted); }} .card {{ border:1px solid var(--border); background:var(--panel); border-radius:11px; padding:16px; margin-top:14px; }} form {{ display:grid; grid-template-columns:2fr 1fr 1fr 1fr; gap:12px; align-items:end; }} label {{ display:grid; gap:5px; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.05em; }} .wide {{ grid-column:1/-1; }} textarea,input,select,button {{ border:1px solid var(--border); border-radius:8px; background:var(--panel2); color:var(--text); padding:10px 11px; font:inherit; }} textarea {{ min-height:78px; resize:vertical; }} button {{ cursor:pointer; background:#2a2411; border-color:#6d5b24; color:#f7d66e; font-weight:760; }} code {{ background:var(--panel2); padding:2px 5px; border-radius:4px; }} table {{ width:100%; border-collapse:collapse; }} th,td {{ padding:9px; border-bottom:1px solid var(--border); text-align:right; }} th:first-child,td:first-child {{ text-align:left; }} th {{ color:var(--muted); font-size:11px; text-transform:uppercase; }} .metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }} .metric {{ font-size:24px; font-weight:760; }} .error {{ border:1px solid #6b2e2e; background:#221111; color:#f3b1b1; padding:12px 14px; border-radius:9px; margin:14px 0; }} .feature-list {{ display:flex; flex-wrap:wrap; gap:7px; margin-top:8px; }} .pill {{ background:var(--panel2); border:1px solid var(--border); border-radius:999px; padding:5px 8px; color:var(--muted); }} .note {{ border-left:3px solid #6d5b24; padding-left:12px; }} @media(max-width:900px) {{ form,.metrics {{ grid-template-columns:1fr; }} .wide {{ grid-column:auto; }} }}
</style></head><body><div class="wrap">
<a href="/">← Research console</a><h1>Strategy Lab</h1>
<div class="subtle">Test safe feature expressions directly against the selected immutable canonical dataset. No provider calls are made. Results are exploratory descriptive research, not validation or a portfolio backtest.</div>
<div class="card"><form action="/research/strategies" method="get">
<label class="wide">Feature expression<textarea name="expression">{escape(expression)}</textarea></label>
<label>Rank feature<select name="rank_feature">{_feature_options(features, rank_feature)}</select></label>
<label>Rank direction<select name="direction"><option value="desc"{" selected" if descending else ""}>Descending</option><option value="asc"{" selected" if not descending else ""}>Ascending</option></select></label>
<label>Per-session limit<input name="limit" type="number" min="1" max="500" value="{limit}"></label>
<label>Signal lookback<select name="lookback_years">{_lookback_options(lookback_years)}</select></label>
<label>Forward horizons<input name="horizons" value="{escape(','.join(str(item) for item in horizons))}" placeholder="5,20,60"></label>
<label class="wide">Optional reviewed symbols<input name="symbols" value="{escape(','.join(selected_symbols))}" placeholder="AAPL,MSFT,NVDA — leave blank for all reviewed canonical instruments"></label>
<div class="wide"><button type="submit">Run strategy research</button></div>
</form></div>
<div class="card"><h2>Available features</h2><div class="feature-list">{''.join(f'<span class="pill">{escape(item)}</span>' for item in features)}</div><div class="subtle" style="margin-top:10px">Expressions allow arithmetic, comparisons, <code>and</code>, <code>or</code>, and <code>not</code>. Function calls, attribute access, indexing, mutation, and arbitrary Python are rejected.</div></div>
<div class="card note"><strong>Universe boundary:</strong> {len(symbols)} reviewed symbols are currently resolvable from the identity candidate. This is the reviewed canonical cohort as supplied; the lab does not invent historical S&amp;P 500 membership or survivorship-bias corrections.</div>
{warning}{results}
</div></body></html>"""


def _empty_state() -> str:
    return '<div class="card"><h2>Ready</h2><div class="subtle">Adjust the expression and run. The engine forms signals point-in-time, ranks independently on each session, enters at the next session open, and measures canonical forward paths.</div></div>'


def _render_report(report: StrategyResearchReport) -> str:
    summary_rows = "".join(
        "<tr>"
        f"<td>{item.horizon} sessions</td>"
        f"<td>{item.sample_size}</td>"
        f"<td>{_percent(item.mean_return)}</td>"
        f"<td>{_percent(item.median_return)}</td>"
        f"<td>{_fraction(item.positive_fraction)}</td>"
        f"<td>{_percent(item.median_mfe)}</td>"
        f"<td>{_percent(item.median_mae)}</td>"
        f"<td>{_drawdown(item.median_drawdown_lower_bound, item.median_drawdown_upper_bound)}</td>"
        "</tr>"
        for item in report.summaries
    )
    signal_rows = "".join(
        "<tr>"
        f"<td>{escape(item.signal_date.isoformat())}</td>"
        f"<td>{escape(str(item.instrument_id))}</td>"
        f"<td>{escape(item.rank_feature)}</td>"
        f"<td>{item.rank_value:.4f}</td>"
        "</tr>"
        for item in report.signals[:50]
    )
    warnings = "".join(f"<li>{escape(item)}</li>" for item in report.warnings)
    return f"""<div class="metrics card"><div><div class="subtle">Canonical instruments</div><div class="metric">{report.instrument_count}</div></div><div><div class="subtle">Selected signals</div><div class="metric">{report.signal_count}</div></div><div><div class="subtle">Measured paths</div><div class="metric">{len(report.outcomes)}</div></div><div><div class="subtle">Research state</div><div class="metric">{escape(report.research_state)}</div></div></div>
<div class="card" style="overflow:auto"><h2>Forward outcome distributions</h2><table><thead><tr><th>Horizon</th><th>N complete</th><th>Mean return</th><th>Median return</th><th>Positive</th><th>Median MFE</th><th>Median MAE</th><th>Median drawdown bounds</th></tr></thead><tbody>{summary_rows}</tbody></table></div>
<div class="card" style="overflow:auto"><h2>First 50 selected signals</h2><div class="subtle">Instrument IDs are permanent canonical identities; symbol labels remain separate identity metadata.</div><table><thead><tr><th>Signal date</th><th>Instrument ID</th><th>Rank feature</th><th>Rank value</th></tr></thead><tbody>{signal_rows}</tbody></table></div>
<div class="card"><h2>Interpretation boundary</h2><ul>{warnings}</ul></div>"""


def _feature_options(features: tuple[str, ...], selected: str) -> str:
    return "".join(
        f'<option value="{escape(item)}"' + (" selected" if item == selected else "") + f">{escape(item)}</option>"
        for item in features
    )


def _lookback_options(selected: int) -> str:
    return "".join(
        f'<option value="{item}"' + (" selected" if item == selected else "") + f">{item} year{"s" if item != 1 else ""}</option>"
        for item in (1, 2, 3, 5, 10, 20)
    )


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _fraction(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _drawdown(lower: float | None, upper: float | None) -> str:
    if lower is None or upper is None:
        return "—"
    if lower == upper:
        return _percent(lower)
    return f"{_percent(lower)} to {_percent(upper)}"


__all__ = ["render_strategy_research_html"]
