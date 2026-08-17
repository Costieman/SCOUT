"""Presentation-only surface for one-variable entry-indicator sweeps."""

from __future__ import annotations

from html import escape

from trade_scout.app.strategy_builder_entry_sweep import StrategyBuilderEntrySweepReport


def attach_entry_sweep_html(html: str, report: StrategyBuilderEntrySweepReport) -> str:
    """Attach a complete entry-parameter response surface to Strategy Builder HTML."""

    marker = "</div></body></html>"
    if marker not in html:
        raise RuntimeError("Strategy Builder renderer omitted its closing application marker")
    return html.replace(marker, _render_entry_sweep(report) + marker, 1)


def _render_entry_sweep(report: StrategyBuilderEntrySweepReport) -> str:
    points = report.points
    if not points:
        return ""
    available = tuple(item for item in points if item.expectancy is not None)
    if not available:
        chart = '<div class="section-note">No complete hold-to-horizon outcomes are available for this sweep.</div>'
    else:
        chart = _expectancy_svg(report)
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
        for item in points
    )
    best = max(available, key=lambda item: float(item.expectancy or 0.0)) if available else None
    best_text = (
        "No complete expectancy estimate is available."
        if best is None
        else (
            f"Highest observed hold expectancy in this declared range: {best.value:g} "
            f"{escape(report.unit_label)} -> {_pct(best.expectancy)}. This identifies a location to inspect; "
            "it is not a validated optimum."
        )
    )
    return f"""<div class="card" id="entry-sweep-results">
<h2>Entry-parameter sweep — {escape(report.parameter_label)}</h2>
<div class="section-note"><strong>Different entry parameters can create different events.</strong> Unlike an exit sweep, N is allowed to change from row to row. SCOUT therefore evaluates each predeclared child definition separately while keeping the universe, other entry rules, ranking, execution assumptions and hold-to-horizon outcome convention fixed.</div>
<div class="section-note"><strong>Research boundary:</strong> this first entry-sweep slice evaluates the entry surface with the hold-to-maximum-period control only. Stops remain a separate research dimension so entry sensitivity is not confounded with simultaneous stop selection.</div>
{chart}
<p><strong>{best_text}</strong></p>
<div class="scroll"><table><thead><tr><th>{escape(report.parameter_label)}</th><th>Entry events</th><th>Complete events</th><th>Hold expectancy</th><th>Win rate</th><th>PF</th><th>P05</th><th>Avg hold</th></tr></thead><tbody>{rows}</tbody></table></div>
<table style="margin-top:12px"><tr><th>Declared values</th><td>{len(report.values)}</td></tr><tr><th>Window</th><td>{report.analysis_start.isoformat()} to {report.analysis_end.isoformat()}</td></tr><tr><th>Dataset</th><td><code>{escape(report.dataset_version)}</code></td></tr><tr><th>Search-space fingerprint</th><td><code>{escape(report.search_space_fingerprint)}</code></td></tr><tr><th>Sweep runtime</th><td>{report.total_seconds:.2f}s</td></tr><tr><th>Research state</th><td>{escape(report.research_state)}</td></tr></table>
</div>"""


def _expectancy_svg(report: StrategyBuilderEntrySweepReport) -> str:
    points = tuple(item for item in report.points if item.expectancy is not None)
    width, height = 920.0, 310.0
    left, right, top, bottom = 72.0, 28.0, 28.0, 58.0
    x_min = min(item.value for item in points)
    x_max = max(item.value for item in points)
    y_values = tuple(float(item.expectancy) * 100.0 for item in points if item.expectancy is not None)
    y_min = min(y_values)
    y_max = max(y_values)
    if y_min == y_max:
        y_min -= 0.5
        y_max += 0.5
    padding = max((y_max - y_min) * 0.12, 0.05)
    y_min -= padding
    y_max += padding

    def x(value: float) -> float:
        fraction = 0.5 if x_max == x_min else (value - x_min) / (x_max - x_min)
        return left + fraction * (width - left - right)

    def y(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * (height - top - bottom)

    polyline = " ".join(
        f"{x(item.value):.1f},{y(float(item.expectancy) * 100.0):.1f}" for item in points
    )
    circles = "".join(
        f'<circle cx="{x(item.value):.1f}" cy="{y(float(item.expectancy) * 100.0):.1f}" r="4.5" fill="#f1c84b"><title>{item.value:g} {escape(report.unit_label)}: expectancy {_pct(item.expectancy)}, complete N={item.complete_event_count}</title></circle>'
        for item in points
    )
    return f"""<svg viewBox="0 0 {width:g} {height:g}" role="img" aria-label="Hold expectancy across {escape(report.parameter_label)} sweep" style="width:100%;min-height:280px;background:#10151d;border:1px solid #293241;border-radius:10px">
<line x1="{left:g}" x2="{left:g}" y1="{top:g}" y2="{height - bottom:g}" stroke="#657184"/>
<line x1="{left:g}" x2="{width - right:g}" y1="{height - bottom:g}" y2="{height - bottom:g}" stroke="#657184"/>
<polyline points="{polyline}" fill="none" stroke="#f1c84b" stroke-width="3"/>{circles}
<text x="{left:g}" y="{height - 20:g}" fill="#98a6b8" font-size="11">{x_min:g}</text>
<text x="{width - right:g}" y="{height - 20:g}" text-anchor="end" fill="#98a6b8" font-size="11">{x_max:g}</text>
<text x="{(left + width - right) / 2:g}" y="{height - 20:g}" text-anchor="middle" fill="#edf1f7" font-size="12">{escape(report.parameter_label)} ({escape(report.unit_label)})</text>
<text transform="translate(18 {(top + height - bottom) / 2:g}) rotate(-90)" text-anchor="middle" fill="#edf1f7" font-size="12">Hold expectancy per trade (%)</text>
<text x="{left:g}" y="{top + 10:g}" fill="#98a6b8" font-size="11">{y_max:+.2f}%</text>
<text x="{left:g}" y="{height - bottom - 6:g}" fill="#98a6b8" font-size="11">{y_min:+.2f}%</text>
</svg>"""


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


def _prob(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


__all__ = ["attach_entry_sweep_html"]
