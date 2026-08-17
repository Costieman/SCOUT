# ruff: noqa: E501
"""Presentation-only surface for one-variable entry-indicator sweeps."""

from __future__ import annotations

from html import escape

from trade_scout.app.strategy_builder_entry_sweep import StrategyBuilderEntrySweepReport
from trade_scout.app.strategy_builder_entry_sweep_chart import render_entry_sweep_chart


def attach_entry_sweep_html(html: str, report: StrategyBuilderEntrySweepReport) -> str:
    """Attach a complete entry-parameter response surface to Strategy Builder HTML."""
    marker = "</div></body></html>"
    if marker not in html:
        raise RuntimeError("Strategy Builder renderer omitted its closing application marker")
    return html.replace(marker, _render_entry_sweep(report) + marker, 1)


def _render_entry_sweep(report: StrategyBuilderEntrySweepReport) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{item.value:g}</td>"
        f"<td>{item.entry_event_count}</td>"
        f"<td>{item.complete_event_count}</td>"
        f"<td>{_pct(item.expectancy)}</td>"
        f"<td>{_prob(item.win_probability)}</td>"
        f"<td>{_num(item.profit_factor)}</td>"
        f"<td>{_pct(item.tail_loss_p05)}</td>"
        f"<td>{_num(item.average_holding_period_sessions)}</td>"
        "</tr>"
        for item in report.points
    )
    available = tuple(item for item in report.points if item.expectancy is not None)
    best = max(available, key=lambda item: float(item.expectancy or 0.0)) if available else None
    best_text = (
        "No complete expectancy estimate is available."
        if best is None
        else f"Highest observed hold expectancy: {best.value:g} {escape(report.unit_label)} -> {_pct(best.expectancy)}. Inspect the surrounding region; this is not a validated optimum."
    )
    return f"""<div class="card" id="entry-sweep-results">
<h2>Entry-parameter sweep — {escape(report.parameter_label)}</h2>
<div class="section-note"><strong>Different entry parameters can create different events.</strong> N may change from row to row. Each declared value is evaluated as its own point-in-time child entry definition while the universe, other entry rules, ranking, execution assumptions and outcome convention stay fixed.</div>
<div class="section-note"><strong>Research boundary:</strong> entry sweeps use hold-to-maximum-period only in this first slice. Stops remain a separate research dimension so entry sensitivity is not mixed with simultaneous stop selection.</div>
{render_entry_sweep_chart(report)}
<p><strong>{best_text}</strong></p>
<div class="scroll"><table><thead><tr><th>{escape(report.parameter_label)}</th><th>Entry events</th><th>Complete events</th><th>Hold expectancy</th><th>Win rate</th><th>PF</th><th>P05</th><th>Avg hold</th></tr></thead><tbody>{rows}</tbody></table></div>
<table style="margin-top:12px"><tr><th>Declared values</th><td>{len(report.values)}</td></tr><tr><th>Window</th><td>{report.analysis_start.isoformat()} to {report.analysis_end.isoformat()}</td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Search-space fingerprint</th><td><code>{escape(report.search_space_fingerprint)}</code></td></tr><tr><th>Sweep runtime</th><td>{report.total_seconds:.2f}s</td></tr><tr><th>Research state</th><td>{escape(report.research_state)}</td></tr></table>
</div>"""


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


def _prob(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


__all__ = ["attach_entry_sweep_html"]
