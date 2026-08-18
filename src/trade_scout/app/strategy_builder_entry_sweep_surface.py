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
        else f"Highest observed hold expectancy: {best.value:g} {escape(report.unit_label)} -> {_pct(best.expectancy)} from {best.complete_event_count:,} complete events. Inspect the surrounding region; this is not a validated optimum."
    )
    return f"""<div class="card" id="entry-sweep-results">
<style>
@media print {{
  #entry-sweep-results svg {{ background:#ffffff !important; border-color:#6b7280 !important; }}
  #entry-sweep-results svg text {{ fill:#111827 !important; }}
  #entry-sweep-results svg .entry-sweep-grid {{ stroke:#cbd5e1 !important; }}
  #entry-sweep-results svg .entry-sweep-axis {{ stroke:#475569 !important; }}
}}
</style>
<h2>Entry-parameter sweep — {escape(report.parameter_label)}</h2>
{_plain_english_summary(report)}
<div class="section-note"><strong>Different entry parameters can create different events.</strong> N may change from row to row. Each declared value is evaluated as its own point-in-time child entry definition while the universe, other entry rules, ranking, execution assumptions and outcome convention stay fixed.</div>
<div class="section-note"><strong>Exit policies applied in this sweep:</strong> none. Any configured stop rows shown above are preserved for later experiments but are not evaluated here. Every child uses the Research Scope maximum holding period as its forced exit so entry sensitivity is not mixed with simultaneous stop selection.</div>
{render_entry_sweep_chart(report)}
<p><strong>{best_text}</strong></p>
{_sample_size_caution(available, best)}
<div class="scroll"><table><thead><tr><th>{escape(report.parameter_label)}</th><th>Entry events</th><th>Complete events</th><th>Hold expectancy</th><th>Win rate</th><th>PF</th><th>P05</th><th>Avg hold</th></tr></thead><tbody>{rows}</tbody></table></div>
<table style="margin-top:12px"><tr><th>Declared values</th><td>{len(report.values)}</td></tr><tr><th>Window</th><td>{report.analysis_start.isoformat()} to {report.analysis_end.isoformat()}</td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Search-space fingerprint</th><td><code>{escape(report.search_space_fingerprint)}</code></td></tr><tr><th>Sweep runtime</th><td>{report.total_seconds:.2f}s</td></tr><tr><th>Research state</th><td>{escape(report.research_state)}</td></tr></table>
</div>"""


def _plain_english_summary(report: StrategyBuilderEntrySweepReport) -> str:
    available = tuple(item for item in report.points if item.expectancy is not None)
    if not available:
        return (
            '<div class="section-note"><strong>What this run says:</strong> '
            "there are no complete hold-to-maximum-period outcomes to interpret yet.</div>"
        )

    best = max(available, key=lambda item: float(item.expectancy or 0.0))
    lowest = min(available, key=lambda item: float(item.expectancy or 0.0))
    spread_pp = (float(best.expectancy or 0.0) - float(lowest.expectancy or 0.0)) * 100.0
    min_value = min(item.value for item in available)
    max_value = max(item.value for item in available)
    edge_note = (
        "The highest observed cell is at the edge of the declared range, so this run does not identify an interior sweet spot."
        if best.value in {min_value, max_value} and len(available) > 1
        else "The highest observed cell is inside the declared range, but this exploratory surface does not establish that it is an optimum."
    )
    expectancy_values = tuple(float(item.expectancy or 0.0) for item in available)
    if min(expectancy_values) > 0:
        sign_note = "Every tested cell had positive historical hold expectancy in this sample."
    elif max(expectancy_values) < 0:
        sign_note = "Every tested cell had negative historical hold expectancy in this sample."
    else:
        sign_note = (
            "The tested range contains both positive and negative historical hold expectancy."
        )
    complete_counts = tuple(item.complete_event_count for item in available)
    count_note = f"Complete-event N ranged from {min(complete_counts):,} to {max(complete_counts):,}, which is expected because changing an entry parameter can change the event population."
    return (
        '<div class="section-note" style="border-left-color:#f1c84b">'
        '<span style="display:inline-block;font-size:11px;font-weight:800;letter-spacing:.05em;color:#f1c84b;border:1px solid #6d5b24;border-radius:999px;padding:3px 7px;margin-bottom:6px">EXPLORATORY PARAMETER MAP</span><br>'
        "<strong>What this run says:</strong> "
        f"Across {len(available)} tested values, hold expectancy ranged from {_pct(lowest.expectancy)} to {_pct(best.expectancy)}, an observed peak-to-trough spread of {spread_pp:.2f} percentage points. "
        f"{sign_note} {edge_note} {count_note} "
        "No uncertainty adjustment, matched comparator, or out-of-sample validation is applied by this entry-sweep view yet; the historical maximum is descriptive only."
        "</div>"
    )


def _sample_size_caution(available: tuple[object, ...], best: object | None) -> str:
    if best is None or not available:
        return ""
    # Keep this a descriptive warning rather than inventing a scientific minimum-N threshold.
    complete_counts = tuple(int(getattr(item, "complete_event_count")) for item in available)
    best_count = int(getattr(best, "complete_event_count"))
    largest_count = max(complete_counts)
    if best_count >= largest_count:
        return ""
    return (
        '<div class="section-note" style="border-left-color:#f2bd60">'
        "<strong>Sample-size caution:</strong> the highest observed expectancy uses "
        f"{best_count:,} complete events, while the largest tested cell uses {largest_count:,}. "
        "Estimates from fewer completed events can move around much more from sample to sample. "
        "SCOUT is not imposing a minimum-N rule here; this is a visible reason not to treat the peak as proven."
        "</div>"
    )


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


def _prob(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


__all__ = ["attach_entry_sweep_html"]
